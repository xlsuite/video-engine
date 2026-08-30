==================================================================
 VIDEO TRANSCRIPT TOOLKIT
 Transcribe footage, then discover themes & quotes. Runs on your
 own computer. Works on any shoot folder you point it at.
==================================================================

WHAT'S IN HERE
  1. Transcribe videos.bat   <- step 1, double-click
  2. Discover themes.bat     <- step 2, double-click
  3. Clip selected.bat       <- step 3 (optional), double-click
  transcribe.py / discover.py / clip.py  (the engines - leave them alone)
  anthropic_key.txt          (created automatically once you enter a key)

KEEP ALL THESE FILES TOGETHER IN THIS FOLDER. You can move the whole
folder anywhere (e.g. your Desktop). The .bat files look for the
engines next to themselves, so don't separate them.

------------------------------------------------------------------
ONE-TIME SETUP
------------------------------------------------------------------
Install Python from https://www.python.org/downloads/
  -> during install, TICK "Add Python to PATH".
Everything else (the transcription engine, etc.) installs itself the
first time you run a step.

------------------------------------------------------------------
HOW TO USE IT (every shoot)
------------------------------------------------------------------
STEP 1 - double-click "1. Transcribe videos.bat"
  - A folder picker opens. Choose the folder with your footage.
  - It transcribes everything into a "transcripts" folder inside it.
  - First run downloads the speech model once. Long jobs can take a
    while on CPU; you can leave it running.

STEP 2 - double-click "2. Discover themes.bat"
  - First time, it asks for your Anthropic API key (paste it into the
    window and press Enter). It saves it so it won't ask again.
    No key? Just press Enter for the free offline pass.
  - A folder picker opens. Choose the SAME shoot folder.
  - It creates a "discovery" folder inside with:
       Quote Index.html   - searchable quotes WITH CHECKBOXES, click-to-copy
       Discovery Brief.md  - themes, people, angles, top soundbites

STEP 3 (optional) - actually cut the clips for your editor
  - Open "discovery\Quote Index.html". Tick the quotes you want, then click
    "Export selection" - it saves clips_to_cut.json to your Downloads.
  - Double-click "3. Clip selected.bat".
       pick that clips_to_cut.json, then pick the SAME shoot folder.
  - It cuts one video per quote into a "clips" folder inside the shoot, plus:
       clips_manifest.csv - each clip -> theme, speaker, quote, source, timecode
       selects.edl        - a timeline that relinks to your ORIGINAL footage
                            in Premiere / Resolve / FCP
  - Each clip gets ~2 seconds of handle on both ends so your editor can trim.
    Change that by editing  set "CLIP_HANDLE=2"  in the .bat.

  NOTE: 360 (.osv) footage can't be auto-clipped (it needs reframing first),
  so any quote that only lives on a 360 cam is skipped with a note. Flat
  footage (action cams, drone, phone, etc.) clips fine.

------------------------------------------------------------------
THE API KEY (for the smart pass)
------------------------------------------------------------------
The SMART pass uses Claude to group quotes by meaning and write the
brief (much better than the offline keyword pass). To enable it:
  1. Get a key at https://platform.claude.com/settings/keys
     (add a little billing credit first under Settings -> Billing).
  2. Run step 2; paste the key when asked. That's it.

The key is stored in anthropic_key.txt in this folder. Treat it like
a password: keep this folder private, and DON'T send anthropic_key.txt
to anyone (e.g. your editor). To change keys, delete that file and
run step 2 again.

------------------------------------------------------------------
TIPS
------------------------------------------------------------------
- Model quality: default is now "large-v3" (best fidelity), running on the GPU.
  To change it, open "1. Transcribe videos.bat" in Notepad and edit
  set "WHISPER_MODEL=..."  (medium or small are faster, lower fidelity).
- GPU: default is  WHISPER_DEVICE=cuda  and the launcher installs the NVIDIA
  CUDA libraries for you. If you run on a machine WITHOUT an NVIDIA GPU, change
  it to  WHISPER_DEVICE=cpu . (If the GPU can't start for any reason, it falls
  back to CPU automatically so the run still finishes.)
- 360 camera files (.OSV/.LRF) are skipped automatically; their
  audio (.WAV) is transcribed instead.
- Timecode accuracy: transcription now uses WORD-LEVEL timestamps, which are
  much tighter than before. Timecodes made by an OLDER run stay loose until you
  re-transcribe those files. To fix just the clips you're cutting without
  redoing everything, re-transcribe only their source files, e.g.:
     python transcribe.py "F:\path\to\shoot" --force --only DJI_20260624064010,DJI_20260624073113
  then re-run step 2 (discover) and step 3 (clip). For the tightest possible
  timing, bump the model to medium or large-v3.
==================================================================
