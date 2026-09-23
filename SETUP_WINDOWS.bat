@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0" || exit /b 1
call "%~dp0scripts\setup_windows.bat"
set "EXIT_CODE=%ERRORLEVEL%"
popd
if not "%EXIT_CODE%"=="0" echo EIA Summary setup failed. Review the error above.
if not defined EIA_NO_PAUSE pause
exit /b %EXIT_CODE%
