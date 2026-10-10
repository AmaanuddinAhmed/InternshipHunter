@echo off
rem Runs the whole pipeline and appends the output to daily.log.
rem Schedule it for early morning with Windows Task Scheduler (see README).
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
set PYTHONUTF8=1
python daily.py >> daily.log 2>&1
