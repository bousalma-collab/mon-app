@echo off
REM ============================================================
REM  CashFlow AI - lancement de l'application
REM  Double-cliquez sur ce fichier ou lancez-le dans PowerShell.
REM ============================================================
setlocal

cd /d "%~dp0"

set "PYTHON_EXE="

REM 1) Python du PATH (py launcher puis python)
where py >nul 2>nul && set "PYTHON_EXE=py -3"
if not defined PYTHON_EXE (
    where python >nul 2>nul && set "PYTHON_EXE=python"
)

REM 2) Sinon, le Python livre avec Thonny (souvent present sur un poste etudiant)
if not defined PYTHON_EXE (
    if exist "%LOCALAPPDATA%\Programs\Thonny\python.exe" (
        set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Thonny\python.exe"
    )
)

if not defined PYTHON_EXE (
    echo.
    echo [ERREUR] Python n'a pas ete trouve sur cet ordinateur.
    echo Installez Python depuis https://www.python.org/downloads/windows/
    echo et cochez "Add python.exe to PATH" pendant l'installation.
    echo.
    pause
    exit /b 1
)

echo Python utilise : %PYTHON_EXE%
echo Verification des dependances...
%PYTHON_EXE% -c "import streamlit, pandas, plotly, openpyxl" 2>nul
if errorlevel 1 (
    echo Installation des dependances manquantes...
    %PYTHON_EXE% -m pip install -r requirements.txt
)

echo.
echo Demarrage de CashFlow AI...
echo L'application va s'ouvrir dans votre navigateur : http://localhost:8501
echo Pour l'arreter : fermez cette fenetre ou appuyez sur Ctrl+C.
echo.
%PYTHON_EXE% -m streamlit run app.py

pause
