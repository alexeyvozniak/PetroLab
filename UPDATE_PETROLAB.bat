@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0"
title PetroLab Update
color 1F

call :banner

if not exist ".git" goto not_git_copy

where git >nul 2>nul
if errorlevel 1 goto git_missing

call :version CURRENT_VERSION
echo.
echo   Installed version: v%CURRENT_VERSION%
echo   Your PetroLab data, Excel files and images will not be touched.
echo.

call :detect_local_changes
if defined PETROLAB_LOCAL_CHANGES goto local_changes

echo   Checking for a new PetroLab version...
git fetch origin main --quiet
if errorlevel 1 goto fetch_failed

for /f %%C in ('git rev-list --count HEAD..origin/main') do set "UPDATE_COUNT=%%C"
if "%UPDATE_COUNT%"=="0" goto already_current

for /f %%H in ('git rev-parse HEAD') do set "BEFORE_UPDATE=%%H"
for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd-HHmmss"') do set "UPDATE_STAMP=%%T"
if not defined UPDATE_STAMP set "UPDATE_STAMP=manual"
git tag "petrolab-before-update-%UPDATE_STAMP%" "%BEFORE_UPDATE%" >nul 2>nul

echo.
echo   A safe restore point has been created.
echo   Installing %UPDATE_COUNT% update(s)...
git merge --ff-only origin/main
if errorlevel 1 goto update_failed

git diff --quiet "%BEFORE_UPDATE%" HEAD -- requirements.txt
if errorlevel 1 (
    echo.
    echo   Updating required Python packages...
    set "PETROLAB_AUTO=1"
    call "%CD%\INSTALL_PETROLAB.bat"
    set "PETROLAB_AUTO="
    if errorlevel 1 goto packages_failed
)

call :version UPDATED_VERSION
echo.
echo   -------------------------------------------------
echo   PetroLab is ready: v%CURRENT_VERSION% to v%UPDATED_VERSION%
echo   -------------------------------------------------
goto ask_launch

:already_current
echo.
echo   -------------------------------------------------
echo   PetroLab v%CURRENT_VERSION% is already up to date.
echo   -------------------------------------------------
goto ask_launch

:ask_launch
echo.
choice /C YN /N /M "   Start PetroLab now? [Y/N]"
if errorlevel 2 goto done
call "%CD%\START_PETROLAB.bat"
goto done

:detect_local_changes
set "PETROLAB_LOCAL_CHANGES="
git diff --ignore-space-at-eol --quiet
if errorlevel 1 set "PETROLAB_LOCAL_CHANGES=1"
git diff --cached --ignore-space-at-eol --quiet
if errorlevel 1 set "PETROLAB_LOCAL_CHANGES=1"
for /f "delims=" %%U in ('git ls-files --others --exclude-standard') do set "PETROLAB_LOCAL_CHANGES=1"
exit /b 0

:version
set "%~1=unknown"
for /f "tokens=2 delims=\"" %%V in ('findstr /b /c:"__version__" "petrolab\__init__.py"') do set "%~1=%%V"
exit /b 0

:banner
echo.
echo   +-------------------------------------------------+
echo   ^|                 PETROLAB UPDATE                ^|
echo   ^|       Safe local update for your workspace     ^|
echo   +-------------------------------------------------+
exit /b 0

:not_git_copy
echo.
echo   This folder is not a GitHub clone, so it cannot update itself.
echo   Download the current PetroLab release into a new folder instead.
goto failed

:git_missing
echo.
echo   Git is not installed or is not available in PATH.
echo   Install Git for Windows, then run this file again.
goto failed

:local_changes
echo.
echo   PetroLab found local code changes and stopped safely.
echo   No files or scientific data were changed.
echo   Save your edits or use a clean program folder, then try again.
goto failed

:fetch_failed
echo.
echo   PetroLab could not check for updates.
echo   Check the Internet connection and try again.
goto failed

:update_failed
echo.
echo   The update was not installed. Your previous restore point is intact.
goto failed

:packages_failed
echo.
echo   Code was updated, but Python packages need attention.
echo   Run DIAGNOSE_PETROLAB.bat for details.
goto failed

:failed
echo.
pause

:done
popd
endlocal
exit /b 0
