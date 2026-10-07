@echo off
rem Thin wrapper so the task runner works from cmd.exe or a double-click:
rem   run.bat all    run.bat pipeline    run.bat status
rem ExecutionPolicy Bypass applies to this one call only.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run.ps1" %*
exit /b %ERRORLEVEL%
