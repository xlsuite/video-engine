@echo off
REM ============================================================
REM  STEP 1 - TRANSCRIBE
REM  Pick a shoot folder; this transcribes every video/audio file
REM  in it (and subfolders) into a "transcripts" folder.
REM  Just double-click. You never need to edit this file.
REM ============================================================
setlocal
cd /d "%~dp0"

REM --- Model: large-v3 (best fidelity) / medium / small = faster ---
set "WHISPER_MODEL=large-v3"
REM --- Where to run: cuda (NVIDIA GPU) or cpu. GPU makes large-v3 fast. ---
set "WHISPER_DEVICE=cuda"

echo.
where python >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not on PATH.
    echo Install from https://www.python.org/downloads/ ^(tick "Add Python to PATH"^).
    pause & exit /b 1
)

echo === Installing / updating the transcription engine (one time) ===
python -m pip install --quiet --upgrade pip
python -m pip install --quiet faster-whisper
if errorlevel 1 (
    echo Could not install faster-whisper. Check your internet connection.
    pause & exit /b 1
)

if /I "%WHISPER_DEVICE%"=="cuda" (
    echo === Installing NVIDIA GPU libraries for CUDA ^(one time^) ===
    python -m pip install --quiet nvidia-cublas-cu12 nvidia-cudnn-cu12
)

REM ---- pick the shoot folder (defaults to this folder if cancelled) ----
echo.
echo Opening folder picker... choose the folder of footage to transcribe.
set "TARGET="
for /f "delims=" %%I in ('powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description='Select the folder of footage to transcribe'; $d.SelectedPath='%~dp0'; if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){Write-Output $d.SelectedPath}"') do set "TARGET=%%I"
if not defined TARGET set "TARGET=%~dp0"
echo Transcribing: %TARGET%

echo.
echo === Starting transcription (model: %WHISPER_MODEL%) ===
echo This can take a while. You can leave it running.
python "%~dp0transcribe.py" "%TARGET%"

echo.
echo === Finished. Now run "2. Discover themes.bat" on the same folder. ===
pause
endlocal
