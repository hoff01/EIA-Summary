@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_daily_release_gate.ps1" %*
