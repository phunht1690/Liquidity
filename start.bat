@echo off
cd /d "%~dp0"
"%USERPROFILE%\.venv\Scripts\python.exe" -m src.app.launcher
if errorlevel 1 pause
