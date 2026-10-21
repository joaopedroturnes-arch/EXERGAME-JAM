@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Instalando o controle pela webcam (MediaPipe e OpenCV). Pode demorar alguns minutos.
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% -m pip install -r requirements-webcam.txt
if errorlevel 1 (
    echo.
    echo A instalacao falhou. O controle pela webcam precisa de Python 3.10 a 3.13.
    pause
    exit /b 1
)
echo.
echo Pronto. No hangar, aperte V para usar a camera.
pause
