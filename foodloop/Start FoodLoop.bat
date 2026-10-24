@echo off
rem Double-click this file to start FoodLoop (database, backend and website). Close the window or press Ctrl+C to stop.
title FoodLoop
cd /d "%~dp0"
set "PY=python"
where py >/dev/null 2>/dev/null && set "PY=py -3"
%PY% run.py %*
if errorlevel 1 (
  echo.
  echo FoodLoop stopped. Read the PROBLEM and FIX lines above.
  echo If it says Python was not found, install Python 3.12+ from python.org and tick "Add python.exe to PATH".
  pause
)
