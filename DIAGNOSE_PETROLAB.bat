@echo off
setlocal EnableExtensions
pushd "%~dp0"

set "VENV_PY=%CD%\.venv\Scripts\python.exe"

echo === PetroLab Windows diagnostics ===
echo Folder: %CD%
echo.

echo [Files]
if exist "%CD%\app.py" (echo OK app.py) else (echo MISSING app.py)
if exist "%CD%\requirements.txt" (echo OK requirements.txt) else (echo MISSING requirements.txt)
if exist "%CD%\INSTALL_PETROLAB.bat" (echo OK installer) else (echo MISSING installer)
if exist "%VENV_PY%" (echo OK virtual environment) else (echo MISSING virtual environment)
echo.

echo [Python launcher]
where py 2>nul || echo py launcher not found
where python 2>nul || echo python command not found
echo.

if exist "%VENV_PY%" (
    echo [Virtual environment Python]
    "%VENV_PY%" --version
    echo.
    echo [Pip dependency check]
    "%VENV_PY%" -m pip check
    echo.
    echo [Streamlit]
    "%VENV_PY%" -m streamlit version
    echo.
    echo [Import check]
    "%VENV_PY%" -c "import pandas,numpy,matplotlib,openpyxl,streamlit; print('OK: core imports')"
    echo.
    echo [PetroLab formula tests]
    "%VENV_PY%" tests_formulae.py
) else (
    echo Virtual environment is absent. Run INSTALL_PETROLAB.bat first.
)

echo.
echo Diagnostics finished.
popd
pause
exit /b 0
