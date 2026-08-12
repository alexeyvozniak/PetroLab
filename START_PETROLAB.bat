@echo off
setlocal EnableExtensions
pushd "%~dp0"

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
set "APP_FILE=%CD%\app.py"

if not exist "%APP_FILE%" (
    echo.
    echo ERROR: app.py was not found in the PetroLab folder.
    goto fail
)

if not exist "%VENV_PY%" (
    echo.
    echo PetroLab is not installed yet. Running installer...
    set "PETROLAB_AUTO=1"
    call "%CD%\INSTALL_PETROLAB.bat"
    set "PETROLAB_AUTO="
    if errorlevel 1 goto fail
)

if not exist "%VENV_PY%" (
    echo.
    echo ERROR: Virtual environment Python was not created.
    goto fail
)

if "%PETROLAB_CI%"=="1" (
    echo.
    echo Running PetroLab CI smoke tests...
    "%VENV_PY%" tests_formulae.py
    if errorlevel 1 goto fail
    "%VENV_PY%" tests_dataframe_utils.py
    if errorlevel 1 goto fail
    "%VENV_PY%" tests_import_service.py
    if errorlevel 1 goto fail
    "%VENV_PY%" tests_analysis_service.py
    if errorlevel 1 goto fail
    "%VENV_PY%" tests_smoke.py
    if errorlevel 1 goto fail
    "%VENV_PY%" tests_streamlit.py
    if errorlevel 1 goto fail
    echo PetroLab CI smoke tests completed successfully.
    popd
    exit /b 0
)

echo.
echo Starting PetroLab...
"%VENV_PY%" -m streamlit run "%APP_FILE%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo ERROR: PetroLab stopped with exit code %EXIT_CODE%.
    echo Run DIAGNOSE_PETROLAB.bat for additional checks.
    goto fail
)

popd
exit /b 0

:fail
popd
if not "%PETROLAB_CI%"=="1" pause
exit /b 1
