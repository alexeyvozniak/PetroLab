@echo off
setlocal EnableExtensions
pushd "%~dp0"
title PetroLab Update
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_petrolab.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %EXIT_CODE%
