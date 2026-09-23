@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0" || exit /b 1
call "%~dp0scripts\setup_windows.bat" -IfNeeded
if errorlevel 1 goto finish
:run
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_daily_release_gate.ps1" -ConfigureRecipients %*
:finish
set "EXIT_CODE=%ERRORLEVEL%"
popd
if not "%EXIT_CODE%"=="0" echo EIA Summary failed. Review the error above and the logs folder.
if not defined EIA_NO_PAUSE if "%~1"=="" pause
exit /b %EXIT_CODE%
