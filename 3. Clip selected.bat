@echo off
REM ============================================================
REM  STEP 3 - CLIP SELECTED QUOTES
REM  After you tick quotes in the Quote Index and click
REM  "Export selection" (saves clips_to_cut.json), run this:
REM    1. pick that clips_to_cut.json
REM    2. pick the shoot folder (where the source videos are)
REM  It cuts a video per quote into <shoot>\clips\ + a manifest + EDL.
REM  Just double-click. You never need to edit this file.
REM ============================================================
setlocal
cd /d "%~dp0"

REM --- seconds of padding added to each end of every clip ---
set "CLIP_HANDLE=2"

echo.
where python >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not on PATH.
    echo Install from https://www.python.org/downloads/ ^(tick "Add Python to PATH"^).
    pause & exit /b 1
)

echo === Installing / updating the clipping engine (one time) ===
python -m pip install --quiet --upgrade imageio-ffmpeg

REM ---- 1. pick the exported selection file ----
echo.
echo Choose the clips_to_cut.json you exported from the Quote Index...
set "SELECTION="
for /f "delims=" %%I in ('powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; $o=New-Object System.Windows.Forms.OpenFileDialog; $o.Title='Pick clips_to_cut.json'; $o.Filter='JSON files (*.json)|*.json|All files (*.*)|*.*'; $o.InitialDirectory=[Environment]::GetFolderPath('UserProfile')+'\Downloads'; if($o.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){Write-Output $o.FileName}"') do set "SELECTION=%%I"
if not defined SELECTION (
    echo No selection file chosen. Exiting.
    pause & exit /b 1
)
echo Selection: %SELECTION%

REM ---- 2. pick the shoot folder (source videos) ----
echo.
echo Choose the shoot folder (the one containing your source video subfolders)...
set "TARGET="
for /f "delims=" %%I in ('powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description='Select the shoot folder (where the source videos live)'; if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){Write-Output $d.SelectedPath}"') do set "TARGET=%%I"
if not defined TARGET (
    echo No shoot folder chosen. Exiting.
    pause & exit /b 1
)
echo Shoot: %TARGET%

REM ---- 3. cut ----
echo.
echo === Cutting clips (handles: %CLIP_HANDLE%s each end) ===
python "%~dp0clip.py" "%SELECTION%" "%TARGET%" --handle %CLIP_HANDLE%

echo.
echo === Done. Open the "clips" folder inside your shoot to hand off to the editor. ===
pause
endlocal
