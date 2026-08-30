#!/usr/bin/env python3
"""
Transcribe every video/audio file in this folder (and subfolders) using Whisper.

Outputs, for each media file, into a `transcripts/` folder that mirrors the
original folder structure:
    - <name>.txt   plain text transcript
    - <name>.srt   subtitle file with timestamps
Also writes one combined file: transcripts/_ALL_TRANSCRIPTS.txt

Re-running is safe: files already transcribed are skipped (use --force to redo).

TIMECODE ACCURACY:
    This uses WORD-LEVEL timestamps (Whisper force-aligns each word to the audio)
    and disables condition_on_previous_text, which together give much tighter,
    more reliable timecodes on long takes than plain segment timestamps.
    Set WHISPER_WORDTS=0 to fall back to the faster (looser) segment timestamps.

Usage (normally you just double-click the .bat, but from a terminal):
    python transcribe.py                 # transcribe this folder
    python transcribe.py "D:\\some\\path" # transcribe a different folder
    python transcribe.py --model medium   # better quality, slower
    python transcribe.py --force          # re-do everything
"""

import os
import sys
import argparse

MEDIA_EXTS = {
    ".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".mpg", ".mpeg",
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wma",
}

# Files we should never try to transcribe (360 raw / proxy / sidecar formats)
SKIP_EXTS = {".osv", ".lrf", ".thm", ".srt", ".txt", ".gpx"}


def fmt_ts(seconds: float) -> str:
    """seconds -> SRT timestamp 00:00:00,000"""
    if seconds is None or seconds < 0:
        seconds = 0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def enable_cuda_dlls():
    """On Windows, make pip-installed NVIDIA cuBLAS/cuDNN DLLs findable so the
    GPU path works without manual PATH setup."""
    if os.name != "nt":
        return
    try:
        import site
        roots = []
        if hasattr(site, "getsitepackages"):
            roots += site.getsitepackages()
        try:
            roots.append(site.getusersitepackages())
        except Exception:
            pass
        for base in roots:
            for sub in (("nvidia", "cublas", "bin"), ("nvidia", "cudnn", "bin")):
                p = os.path.join(base, *sub)
                if os.path.isdir(p):
                    try:
                        os.add_dll_directory(p)
                    except Exception:
                        pass
    except Exception:
        pass


def pick_device():
    """Choose where to run. Set WHISPER_DEVICE=cpu / cuda / auto to force it."""
    forced = os.environ.get("WHISPER_DEVICE", "auto").strip().lower()
    if forced == "cpu":
        return "cpu", "int8"
    if forced == "cuda":
        return "cuda", "float16"
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def find_media(root: str):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.lower() != "transcripts"]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in MEDIA_EXTS and ext not in SKIP_EXTS:
                out.append(os.path.join(dirpath, fn))
    out.sort()
    return out


def cues_from_words(segments, full_text_parts):
    """Consume the segments generator once, returning word-accurate SRT cues.

    Returns list of (start, end, text). Falls back to segment timing for any
    segment that has no word data.
    """
    cues = []
    buf = []  # list of (start, end, word)

    def flush():
        if buf:
            cues.append((buf[0][0], buf[-1][1], "".join(w[2] for w in buf).strip()))
            buf.clear()

    for seg in segments:
        full_text_parts.append(seg.text.strip())
        words = getattr(seg, "words", None)
        if not words:
            flush()
            cues.append((seg.start, seg.end, seg.text.strip()))
            continue
        for w in words:
            if w.start is None or w.end is None:
                continue
            buf.append((w.start, w.end, w.word))
            txt = "".join(x[2] for x in buf).strip()
            if (txt.endswith((".", "?", "!")) and len(buf) >= 4) or len(buf) >= 14:
                flush()
    flush()
    return cues


def cues_from_segments(segments, full_text_parts):
    cues = []
    for seg in segments:
        full_text_parts.append(seg.text.strip())
        cues.append((seg.start, seg.end, seg.text.strip()))
    return cues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=os.path.dirname(os.path.abspath(__file__)),
                    help="Folder to scan (defaults to where this script lives).")
    ap.add_argument("--model", default=os.environ.get("WHISPER_MODEL", "large-v3"),
                    help="tiny, base, small, medium, large-v3 (bigger = more accurate, slower).")
    ap.add_argument("--language", default=os.environ.get("WHISPER_LANG", ""),
                    help="Force a language code (e.g. en). Default: auto-detect.")
    ap.add_argument("--force", action="store_true",
                    help="Re-transcribe files even if a transcript already exists.")
    ap.add_argument("--only", default="",
                    help="Comma-separated text; only process files whose path contains one "
                         "of these (e.g. --only DJI_20260624064010,DJI_20260624073113). "
                         "Handy for re-doing just the clips you're cutting.")
    args = ap.parse_args()

    cleaned = args.root.strip().strip('"').rstrip("\\/")
    root = os.path.abspath(cleaned)
    if not os.path.isdir(root):
        print(f"ERROR: not a folder: {root}")
        sys.exit(1)

    enable_cuda_dlls()
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("ERROR: faster-whisper is not installed.  Run:  pip install faster-whisper")
        sys.exit(1)

    media = find_media(root)
    only = [s.strip().lower() for s in args.only.split(",") if s.strip()]
    if only:
        media = [p for p in media if any(s in p.lower() for s in only)]
    if not media:
        print(f"No matching video/audio files found under: {root}")
        return

    word_ts = os.environ.get("WHISPER_WORDTS", "1").strip() != "0"
    device, compute_type = pick_device()
    print("=" * 70)
    print(f"Folder      : {root}")
    print(f"Files found : {len(media)}")
    print(f"Model       : {args.model}")
    print(f"Running on  : {device.upper()}  ({compute_type})")
    print(f"Timecodes   : {'word-level (accurate)' if word_ts else 'segment-level (fast)'}")
    if device == "cpu":
        print("Note        : CPU mode is slower; word-level timing adds some time but")
        print("              is worth it for timecode accuracy. Leave it running.")
    print("=" * 70)

    out_root = os.path.join(root, "transcripts")
    os.makedirs(out_root, exist_ok=True)
    master_path = os.path.join(out_root, "_ALL_TRANSCRIPTS.txt")

    print("Loading model (first run downloads it once)...")
    try:
        model = WhisperModel(args.model, device=device, compute_type=compute_type)
    except Exception as e:
        if device != "cpu":
            print(f"  ! GPU load failed ({e}).")
            print("    Falling back to CPU so the run still completes.")
            device, compute_type = "cpu", "int8"
            model = WhisperModel(args.model, device=device, compute_type=compute_type)
        else:
            raise
    language = args.language.strip() or None

    done = skipped = failed = 0
    for i, path in enumerate(media, 1):
        rel = os.path.relpath(path, root)
        base = os.path.splitext(rel)[0]
        txt_path = os.path.join(out_root, base + ".txt")
        srt_path = os.path.join(out_root, base + ".srt")
        os.makedirs(os.path.dirname(txt_path), exist_ok=True)

        if not args.force and os.path.exists(txt_path):
            print(f"[{i}/{len(media)}] SKIP (already done): {rel}")
            skipped += 1
            continue

        print(f"[{i}/{len(media)}] Transcribing: {rel}")
        try:
            segments, info = model.transcribe(
                path, language=language, vad_filter=True,
                word_timestamps=word_ts,
                condition_on_previous_text=False,
            )
            full_text_parts = []
            cues = (cues_from_words(segments, full_text_parts) if word_ts
                    else cues_from_segments(segments, full_text_parts))
            with open(srt_path, "w", encoding="utf-8") as srt:
                for n, (start, end, text) in enumerate(cues, 1):
                    srt.write(f"{n}\n{fmt_ts(start)} --> {fmt_ts(end)}\n{text}\n\n")
            full_text = " ".join(full_text_parts).strip()
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(full_text + "\n")
            with open(master_path, "a", encoding="utf-8") as m:
                m.write("\n" + "=" * 70 + "\n")
                m.write(f"FILE: {rel}\n")
                m.write(f"Detected language: {info.language} "
                        f"(p={info.language_probability:.2f})\n")
                m.write("=" * 70 + "\n")
                m.write(full_text + "\n")
            print(f"           -> {os.path.relpath(txt_path, root)}  (lang: {info.language})")
            done += 1
        except Exception as e:
            print(f"           !! FAILED: {e}")
            failed += 1

    print("=" * 70)
    print(f"Done. Transcribed: {done}  |  Skipped: {skipped}  |  Failed: {failed}")
    print(f"Transcripts are in: {out_root}")
    print("=" * 70)


if __name__ == "__main__":
    main()
