@echo off
cd /d "%~dp0"
py -3 run_all_pairs.py
if errorlevel 1 python run_all_pairs.py
pause
