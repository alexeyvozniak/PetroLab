@echo off
setlocal EnableExtensions
pushd "%~dp0"
title PetroLab Diagnostics

set "ROOT=%CD%"
set "CURRENT=%ROOT%\current"
set "PY=%ROOT%\runtime\python.exe"
set "LAUNCHER=%ROOT%\PetroLab.exe"
set "LOG=%ROOT%\logs\launcher.log"
set "PETROLAB_DATA_DIR=%USERPROFILE%\Documents\PetroLab Data"

echo.
echo   +-----------------------------------------------+
echo   ^|             PETROLAB DIAGNOSTICS             ^|
echo   +-----------------------------------------------+
echo.
echo   Install folder: %ROOT%
echo   Data folder:    %PETROLAB_DATA_DIR%
echo   Launcher log:   %LOG%

if exist "%CURRENT%\.petrolab_build_sha" (
    set /p BUILD=<"%CURRENT%\.petrolab_build_sha"
    echo   Build:          %BUILD%
) else (
    echo   Build:          unknown
)

echo.
echo   [1/5] Native launcher
if not exist "%LAUNCHER%" (
    echo   ERROR: PetroLab.exe is missing.
    goto fail
)
echo   PetroLab.exe present.

echo.
echo   [2/5] Python runtime
if not exist "%PY%" (
    echo   ERROR: embedded Python runtime is missing.
    goto fail
)
"%PY%" --version
if errorlevel 1 goto fail

if not exist "%CURRENT%\app.py" (
    echo.
    echo   ERROR: current\app.py is missing.
    goto fail
)

echo.
echo   [3/5] Installed packages
"%PY%" -m pip check
if errorlevel 1 goto fail

echo.
echo   [4/5] Core imports
pushd "%CURRENT%"
"%PY%" -c "import petrolab, pandas, numpy, streamlit, plotly, sklearn; print('PetroLab', petrolab.__version__); print('Core imports OK')"
set "IMPORT_EXIT=%ERRORLEVEL%"
popd
if not "%IMPORT_EXIT%"=="0" goto fail

echo.
echo   [5/5] Storage bootstrap
if not exist "%PETROLAB_DATA_DIR%" mkdir "%PETROLAB_DATA_DIR%"
pushd "%CURRENT%"
"%PY%" -c "from petrolab.storage import ensure_storage; ensure_storage(); print('Storage OK')"
set "STORAGE_EXIT=%ERRORLEVEL%"
popd
if not "%STORAGE_EXIT%"=="0" goto fail

echo.
echo   PetroLab diagnostics completed successfully.
if exist "%LOG%" (
    echo.
    echo   Last launcher messages:
    powershell.exe -NoProfile -Command "Get-Content -LiteralPath '%LOG%' -Tail 12"
)
goto done

:fail
echo.
echo   PetroLab diagnostics found a problem.
echo   Re-run the latest installer if the launcher, runtime or app files are missing.
if exist "%LOG%" (
    echo.
    echo   Last launcher messages:
    powershell.exe -NoProfile -Command "Get-Content -LiteralPath '%LOG%' -Tail 30"
)

:done
echo.
pause
popd
endlocal
