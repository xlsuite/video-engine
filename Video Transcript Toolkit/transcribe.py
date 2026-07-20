#!/usr/bin/env python3
"""
Transcribe every video/audio file in this folder (and subfolders) using Whisper.

Outputs, for each media file, into a `transcripts/` folder that mirrors the
original folder structure:
    - <name>.txt   plain text transcript
    - <name>.srt   subtitle file with timestamps
Also writes one combined file: transcripts/_ALL_TRANSCRIPTS.txt

Re-running is safe: files already transcribed are skipped (use --force to redo).

Usage (normally you just double-click the .bat, but from a terminal):
    python transcribe.py                 # transcribe this folder
    python transcribe.py "D:\\some\\path" # transcribe a different folder
    python transcribe.py --model medium   # better quality, slower
    python transcribe.py --force          # re-do everything
"""

import os
import sys
import argparse
import datetime

MEDIA_EXTS = {
    ".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm", ".mpg", ".mpeg",
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wma",
}

# Files we should never try to transcribe (360 raw / proxy / sidecar formats)
SKIP_EXTS = {".osv", ".lrf", ".thm", ".srt", ".txt", ".gpx"}


def fmt_ts(seconds: float) -> str:
    """seconds -> SRT timestamp 00:00:00,000"""
    if seconds < 0:
        seconds = 0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def pick_device():
    """Choose where to run.

    Set the WHISPER_DEVICE env var to force it:
      cpu   -> always CPU (safe, no GPU drivers needed)
      cuda  -> always GPU (needs CUDA cuBLAS + cuDNN DLLs installed)
      auto  -> use GPU only if CUDA is detected (default)
    """
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
        # don't descend into our own output folder
        dirnames[:] = [d for d in dirnames if d.lower() != "transcripts"]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in MEDIA_EXTS and ext not in SKIP_EXTS:
                out.append(os.path.join(dirpath, fn))
    out.sort()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=os.path.dirname(os.path.abspath(__file__)),
                    help="Folder to scan (defaults to where this script lives).")
    ap.add_argument("--model", default=os.environ.get("WHISPER_MODEL", "small"),
                    help="Whisper model: tiny, base, small, medium, large-v3 "
                         "(bigger = more accurate but slower). Default: small")
    ap.add_argument("--language", default=os.environ.get("WHISPER_LANG", ""),
                    help="Force a language code (e.g. en). Default: auto-detect.")
    ap.add_argument("--force", action="store_true",
                    help="Re-transcribe files even if a transcript already exists.")
    args = ap.parse_args()

    # strip stray quotes/whitespace that Windows batch can append to a path
    cleaned = args.root.strip().strip('"').rstrip("\\/")
    root = os.path.abspath(cleaned)
    if not os.path.isdir(root):
        print(f"ERROR: not a folder: {root}")
        sys.exit(1)

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("ERROR: faster-whisper is not installed.")
        print("Run:  pip install faster-whisper")
        sys.exit(1)

    media = find_media(root)
    if not media:
        print(f"No video/audio files found under: {root}")
        return

    device, compute_type = pick_device()
    print("=" * 70)
    print(f"Folder      : {root}")
    print(f"Files found : {len(media)}")
    print(f"Model       : {args.model}")
    print(f"Running on  : {device.upper()}  ({compute_type})")
    if device == "cpu":
        print("Note        : no GPU detected -> running on CPU. This is slower.")
        print("              For ~3h of audio expect roughly 1-4h on a modern CPU")
        print("              with the 'small' model. 'medium'/'large-v3' are slower.")
    print("=" * 70)

    out_root = os.path.join(root, "transcripts")
    os.makedirs(out_root, exist_ok=True)
    master_path = os.path.join(out_root, "_ALL_TRANSCRIPTS.txt")

    print("Loading model (first run downloads it once)...")
    model = WhisperModel(args.model, device=device, compute_type=compute_type)
    language = args.language.strip() or None

    done = 0
    skipped = 0
    failed = 0

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
            segments, info = model.transcribe(path, language=language, vad_filter=True)
            full_text_parts = []
            with open(srt_path, "w", encoding="utf-8") as srt:
                for n, seg in enumerate(segments, 1):
                    line = seg.text.strip()
                    full_text_parts.append(line)
                    srt.write(f"{n}\n{fmt_ts(seg.start)} --> {fmt_ts(seg.end)}\n{line}\n\n")
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
            print(f"           -> {os.path.relpath(txt_path, root)}  "
                  f"(lang: {info.language})")
            done += 1
        except Exception as e:
            print(f"           !! FAILED: {e}")
            failed += 1

    print("=" * 70)
    print(f"Done. Transcribed: {done}  |  Skipped: {skipped}  |  Failed: {failed}")
    print(f"Transcripts are in: {out_root}")
    print(f"Combined file     : {master_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
