@echo off
REM ============================================================
REM  STEP 2 - DISCOVER THEMES
REM  Run this AFTER step 1. It will:
REM    1. ask for your Anthropic API key the first time (then remember it)
REM    2. let you pick which shoot folder to analyze
REM    3. build  <folder>\discovery\Quote Index.html + Discovery Brief.md
REM  Just double-click. You never need to edit this file.
REM ============================================================
setlocal
cd /d "%~dp0"

set "ANTHROPIC_MODEL=claude-sonnet-4-6"
set "KEYFILE=%~dp0anthropic_key.txt"

echo.
where python >nul 2>&1
if errorlevel 1 (
    echo Python is not installed or not on PATH.
    echo Install from https://www.python.org/downloads/ ^(tick "Add Python to PATH"^).
    pause & exit /b 1
)

REM ---- 1. API key: use existing env var, else saved file, else ask ----
if not defined ANTHROPIC_API_KEY if exist "%KEYFILE%" set /p ANTHROPIC_API_KEY=<"%KEYFILE%"
if defined ANTHROPIC_API_KEY goto :havekey
echo No API key saved yet.
echo Paste your Anthropic API key below for the SMART pass, or just press
echo ENTER to skip and use the free offline keyword pass.
echo (Get a key at https://platform.claude.com/settings/keys )
set /p "ANTHROPIC_API_KEY=Key: "
if not defined ANTHROPIC_API_KEY goto :havekey
> "%KEYFILE%" echo %ANTHROPIC_API_KEY%
echo Saved to anthropic_key.txt - I won't ask again. Keep that file private.
:havekey

if "%ANTHROPIC_API_KEY%"=="" (
    echo Mode: OFFLINE  ^(no key - keyword grouping^)
) else (
    echo Mode: SMART  ^(Claude groups themes and writes the brief^)
)

REM ---- 2. pick the shoot folder (defaults to this folder if cancelled) ----
echo.
echo Opening folder picker... choose the shoot folder (the one that
echo contains a "transcripts" folder from step 1).
set "TARGET="
for /f "delims=" %%I in ('powershell -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.FolderBrowserDialog; $d.Description='Select the shoot folder (must contain a transcripts folder)'; $d.SelectedPath='%~dp0'; if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){Write-Output $d.SelectedPath}"') do set "TARGET=%%I"
if not defined TARGET set "TARGET=%~dp0"
echo Analyzing: %TARGET%

REM ---- 3. dependencies + run ----
echo.
echo === Installing / updating dependencies (one time) ===
python -m pip install --quiet --upgrade anthropic

echo.
echo === Analyzing transcripts ===
python "%~dp0discover.py" "%TARGET%"

echo.
echo === Done. Open the "discovery" folder inside that shoot for your files. ===
pause
endlocal
