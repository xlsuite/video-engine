#!/usr/bin/env python3
"""
CLIP — cut the quotes you selected in the Quote Index.

Inputs:
  1. clips_to_cut.json  (exported from the Quote Index "Export selection" button)
  2. the shoot folder    (the one containing your source video subfolders)

Outputs, into  <shoot folder>\\clips\\ :
  - one video per selected quote (stream-copied, fast + lossless), with a couple
    of seconds of handle on each end
  - clips_manifest.csv  (each clip -> theme, who, text, source file, timecodes)
  - selects.edl         (CMX3600 timeline referencing your ORIGINAL media)

Usage:
  python clip.py clips_to_cut.json "D:\\shoot folder"
  python clip.py clips_to_cut.json "D:\\shoot folder" --handle 3
"""

import os
import re
import sys
import csv
import json
import shutil
import argparse
import subprocess
from collections import defaultdict

VIDEO_EXTS = [".mp4", ".mov", ".mkv", ".m4v", ".avi", ".webm", ".mpg", ".mpeg"]
NOVIDEO_EXTS = [".osv", ".wav", ".m4a", ".mp3", ".aac", ".flac"]  # 360 raw / audio-only


def find_ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def fps_of(path, default=30.0):
    try:
        import av
        with av.open(path) as c:
            r = c.streams.video[0].average_rate
            if r:
                return float(r)
    except Exception:
        pass
    return default


def slug(text, n=48):
    s = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return (s[:n].rstrip("-")) or "clip"


def index_videos(root):
    """basename(no ext, lower) -> list of full paths (video files only)."""
    by_base = defaultdict(list)
    other = defaultdict(list)  # 360/audio, for helpful warnings
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d.lower() not in ("transcripts", "discovery", "clips")]
        for fn in fns:
            base, ext = os.path.splitext(fn)
            ext = ext.lower()
            full = os.path.join(dp, fn)
            if ext in VIDEO_EXTS:
                by_base[base.lower()].append(full)
            elif ext in NOVIDEO_EXTS:
                other[base.lower()].append(full)
    return by_base, other


def resolve(clip_id, by_base, other, root):
    """Map a quote's clip id to a real source video path (or a reason it can't)."""
    base = clip_id.rsplit("__", 1)[-1].lower()
    cands = by_base.get(base, [])
    if len(cands) > 1 and "__" in clip_id:
        folder = clip_id.rsplit("__", 1)[0].replace("__", os.sep).lower()
        pref = [c for c in cands if folder in os.path.dirname(c).lower()]
        if pref:
            cands = pref
    if cands:
        return cands[0], None
    if base in other:
        ex = os.path.splitext(other[base][0])[1].lower()
        if ex == ".osv":
            return None, "360 footage (.osv) - needs reframing, can't auto-clip"
        return None, "audio-only source - no video to clip"
    return None, "source video not found"


def sec_to_edl_tc(sec, fps):
    sec = max(0.0, sec)
    f = int(round((sec - int(sec)) * fps))
    s = int(sec)
    if f >= int(round(fps)):
        f = 0
        s += 1
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}:{f:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("selection", help="clips_to_cut.json exported from the index")
    ap.add_argument("root", help="the shoot folder (contains the source videos)")
    ap.add_argument("--handle", type=float,
                    default=float(os.environ.get("CLIP_HANDLE", "2")),
                    help="seconds of padding added to each end (default 2)")
    args = ap.parse_args()

    sel_path = args.selection.strip().strip('"')
    root = os.path.abspath(args.root.strip().strip('"').rstrip("\\/"))
    handle = max(0.0, args.handle)

    if not os.path.isfile(sel_path):
        print(f"ERROR: selection file not found: {sel_path}")
        sys.exit(1)
    if not os.path.isdir(root):
        print(f"ERROR: not a folder: {root}")
        sys.exit(1)

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        print("ERROR: ffmpeg not found. Run:  pip install imageio-ffmpeg")
        sys.exit(1)

    with open(sel_path, encoding="utf-8") as f:
        sel = json.load(f)
    if not isinstance(sel, list) or not sel:
        print("Selection is empty. Tick some quotes and Export again.")
        return

    print(f"Selection : {len(sel)} clips")
    print(f"Shoot     : {root}")
    print(f"Handles   : {handle}s each end")
    print("Indexing source videos...")
    by_base, other = index_videos(root)

    out_dir = os.path.join(root, "clips")
    os.makedirs(out_dir, exist_ok=True)

    rows = []        # for manifest + edl
    made = skipped = 0
    seq = 0
    for item in sel:
        clip_id = item.get("clip", "")
        in_sec = float(item.get("in_sec", 0))
        out_sec = float(item.get("out_sec", in_sec + 2))
        theme = item.get("theme", "Other")
        who = item.get("who", "")
        text = item.get("text", "")

        src, reason = resolve(clip_id, by_base, other, root)
        if not src:
            print(f"  SKIP  {clip_id}: {reason}")
            skipped += 1
            continue

        seq += 1
        a = max(0.0, in_sec - handle)
        b = out_sec + handle
        dur = max(0.5, b - a)
        ext = os.path.splitext(src)[1].lower()
        name = f"{seq:02d}_{slug(theme,24)}_{slug(text)}{ext}"
        dest = os.path.join(out_dir, name)

        cmd = [ffmpeg, "-y", "-ss", f"{a:.3f}", "-i", src, "-t", f"{dur:.3f}",
               "-c", "copy", "-avoid_negative_ts", "make_zero",
               "-loglevel", "error", dest]
        print(f"  [{seq}] {name}")
        try:
            subprocess.run(cmd, check=True)
            made += 1
            rows.append({
                "seq": seq, "file": name, "theme": theme, "who": who, "text": text,
                "source": os.path.relpath(src, root),
                "src_path": src,
                "in_sec": round(a, 3), "out_sec": round(b, 3),
                "in_tc": item.get("in_tc", ""), "out_tc": item.get("out_tc", ""),
            })
        except subprocess.CalledProcessError as e:
            print(f"        !! ffmpeg failed: {e}")
            skipped += 1

    # ---- manifest CSV ----
    man = os.path.join(out_dir, "clips_manifest.csv")
    with open(man, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["#", "clip file", "theme", "speaker", "quote",
                    "source file", "in (s)", "out (s)", "quote in tc", "quote out tc"])
        for r in rows:
            w.writerow([r["seq"], r["file"], r["theme"], r["who"], r["text"],
                        r["source"], r["in_sec"], r["out_sec"], r["in_tc"], r["out_tc"]])

    # ---- EDL (CMX3600), referencing ORIGINAL media ----
    edl = os.path.join(out_dir, "selects.edl")
    fps = fps_of(rows[0]["src_path"], 30.0) if rows else 30.0
    with open(edl, "w", encoding="utf-8") as f:
        f.write("TITLE: SELECTS\nFCM: NON-DROP FRAME\n")
        rec = 0.0
        for r in rows:
            d = r["out_sec"] - r["in_sec"]
            reel = re.sub(r"[^A-Za-z0-9]", "", os.path.splitext(r["file"])[0])[:8].upper() or "CLIP"
            f.write(f"\n{r['seq']:03d}  {reel:<8} V     C        "
                    f"{sec_to_edl_tc(r['in_sec'],fps)} {sec_to_edl_tc(r['out_sec'],fps)} "
                    f"{sec_to_edl_tc(rec,fps)} {sec_to_edl_tc(rec+d,fps)}\n")
            f.write(f"* FROM CLIP NAME: {os.path.basename(r['src_path'])}\n")
            rec += d

    print("=" * 64)
    print(f"Made {made} clips  |  skipped {skipped}")
    print(f"  Clips     : {out_dir}")
    print(f"  Manifest  : {man}")
    print(f"  Timeline  : {edl}  (EDL @ {fps:.0f} fps, relinks by clip name)")
    print("=" * 64)


if __name__ == "__main__":
    main()
