@echo off
cd /d "%~dp0"
set "MAPA_PYTHON=%~dp0.venv\Scripts\python.exe"
if exist "%MAPA_PYTHON%" goto executar
set "MAPA_PYTHON=%~dp0..\Wifi_Heatmap\.venv\Scripts\python.exe"
if exist "%MAPA_PYTHON%" goto executar
python -m venv .venv
if errorlevel 1 goto erro
set "MAPA_PYTHON=%~dp0.venv\Scripts\python.exe"
"%MAPA_PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 goto erro
:executar
if exist "..\planta1.png" (
  "%MAPA_PYTHON%" app.py "..\planta1.png"
) else (
  "%MAPA_PYTHON%" app.py
)
if errorlevel 1 goto erro
exit /b
:erro
echo Nao foi possivel iniciar. Instale Python 3.11 ou superior com Tkinter e execute pip install -r requirements.txt.
pause
