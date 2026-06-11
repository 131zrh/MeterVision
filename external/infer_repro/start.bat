@echo off
REM =====================================================
REM  Pressure Gauge Reader - One-click launcher
REM  Double-click to start the GUI.
REM  Works from any location: uses %~dp0 (script directory).
REM =====================================================

setlocal
chcp 65001 >nul
cd /d "%~dp0"

REM --- 1) Preferred: use the conda env 'yolov11' (what you used during development) ---
set "CONDA_PY=C:\Users\DELL\.conda\envs\yolov11\pythonw.exe"
set "CONDA_PY_CONSOLE=C:\Users\DELL\.conda\envs\yolov11\python.exe"

if exist "%CONDA_PY%" (
    echo [start.bat] Launching with conda env: yolov11 ...
    start "" "%CONDA_PY%" "%~dp0gui_pyside6.py"
    exit /b 0
)

REM --- 2) Fallback: try system 'python' on PATH ---
where python >nul 2>nul
if %errorlevel%==0 (
    echo [start.bat] conda env not found, falling back to system python ...
    start "" python "%~dp0gui_pyside6.py"
    exit /b 0
)

REM --- 3) Nothing worked ---
echo.
echo [start.bat] ERROR: No Python interpreter found.
echo.
echo Please install one of the following and try again:
echo   a) Conda env 'yolov11' at: %CONDA_PY_CONSOLE%
echo   b) Any Python (>= 3.10) on your system PATH
echo      (then run: pip install -r requirements.txt)
echo.
pause
exit /b 1
