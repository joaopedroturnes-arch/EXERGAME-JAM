@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% -c "import pygame" >nul 2>nul || (
    echo Instalando o pygame, isso so acontece na primeira vez...
    %PY% -m pip install -r requirements.txt
)
%PY% eco_runner.py
if errorlevel 1 (
    echo.
    echo O jogo encerrou com erro. Verifique se o Python 3.10 a 3.13 esta instalado.
    pause
)
