@echo off
setlocal EnableExtensions
pushd "%~dp0"

set "VENV_DIR=%CD%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "REQ_FILE=%CD%\requirements.txt"

if not exist "%REQ_FILE%" (
    echo.
    echo ERROR: requirements.txt was not found.
    goto fail
)

if exist "%VENV_PY%" goto install_packages

where py >nul 2>nul
if not errorlevel 1 (
    py -3.12 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        py -3.12 -m venv "%VENV_DIR%"
        if errorlevel 1 goto venv_error
        goto install_packages
    )
    py -3.11 -c "import sys" >nul 2>nul
    if not errorlevel 1 (
        py -3.11 -m venv "%VENV_DIR%"
        if errorlevel 1 goto venv_error
        goto install_packages
    )
    py -3 -m venv "%VENV_DIR%"
    if errorlevel 1 goto venv_error
    goto install_packages
)

where python >nul 2>nul
if not errorlevel 1 (
    python -m venv "%VENV_DIR%"
    if errorlevel 1 goto venv_error
    goto install_packages
)

echo.
echo ERROR: Python 3 was not found.
echo Install Python 3.11 or 3.12 from python.org and enable Add Python to PATH.
goto fail

:install_packages
if not exist "%VENV_PY%" goto venv_error

"%VENV_PY%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
    echo.
    echo ERROR: PetroLab requires Python 3.10 or newer.
    goto fail
)

echo.
echo [1/3] Python version:
"%VENV_PY%" --version

echo.
echo [2/3] Updating pip...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 goto pip_error

echo.
echo [3/3] Installing PetroLab dependencies...
"%VENV_PY%" -m pip install -r "%REQ_FILE%"
if errorlevel 1 goto pip_error

"%VENV_PY%" -m pip check
if errorlevel 1 goto pip_error

echo.
echo PetroLab installation completed successfully.
echo You can now run START_PETROLAB.bat
popd
if not "%PETROLAB_AUTO%"=="1" pause
exit /b 0

:venv_error
echo.
echo ERROR: Could not create the Python virtual environment.
goto fail

:pip_error
echo.
echo ERROR: Could not install or validate Python packages.
echo Check your Internet connection and the messages above.
goto fail

:fail
popd
if not "%PETROLAB_AUTO%"=="1" pause
exit /b 1
