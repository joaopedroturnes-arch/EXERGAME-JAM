@echo off
rem ============================================================================
rem  build_windows.bat - gera o executavel do Eco Runner com PyInstaller
rem
rem  Uso:
rem    build_windows.bat            gera dist\EcoRunner\EcoRunner.exe (onedir, padrao)
rem    build_windows.bat onefile    gera dist\EcoRunner.exe (arquivo unico)
rem    build_windows.bat nopause    nao espera tecla no final (uso automatizado)
rem    Os argumentos podem ser combinados: build_windows.bat onefile nopause
rem
rem  Requisitos: Python 3 para Windows (launcher py ou python no PATH).
rem  O PyInstaller nao faz compilacao cruzada: gere o .exe neste Windows.
rem
rem  Assets: o EcoRunner.spec ja empacota assets\ no executavel (em
rem  _internal\assets no onedir). Por isso assets\ NAO e copiado para
rem  dist\EcoRunner\assets\. O jogo tambem procura assets\ ao lado do .exe,
rem  antes do pacote: para trocar um sprite sem recompilar, basta colocar o
rem  PNG em dist\EcoRunner\assets\<pasta>\<nome>.png.
rem
rem  Variavel opcional: ECO_CONSOLE=1 mantem a janela de console (depuracao).
rem  Aviso: se o self-test falhar, o executavel sem console mostra uma caixa
rem  de mensagem, que so fecha quando for confirmada.
rem ============================================================================
setlocal EnableExtensions

set "ONEFILE=0"
set "NOPAUSE=0"
for %%A in (%*) do (
    if /i "%%~A"=="onefile" set "ONEFILE=1"
    if /i "%%~A"=="nopause" set "NOPAUSE=1"
)

cd /d "%~dp0"
if errorlevel 1 goto :fail_cd

if "%ONEFILE%"=="1" (
    set "MODO=onefile"
    set "EXE=dist\EcoRunner.exe"
    set "OUT_DIR=dist"
) else (
    set "MODO=onedir"
    set "EXE=dist\EcoRunner\EcoRunner.exe"
    set "OUT_DIR=dist\EcoRunner"
)

rem Relatorio do self-test: pasta de dados do jogo (ver user_data_dir no eco_runner.py).
set "REPORT=%APPDATA%\EcoRunner\self_test.json"
if defined ECO_RUNNER_DATA_DIR set "REPORT=%ECO_RUNNER_DATA_DIR%\self_test.json"

echo [1/5] Procurando Python 3 e preparando o ambiente virtual .venv...
set "PY="
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY goto :fail_python

set "VENV_PY=%CD%\.venv\Scripts\python.exe"
if exist "%VENV_PY%" goto :venv_ok
%PY% -m venv .venv
if errorlevel 1 goto :fail_venv
:venv_ok

echo [2/5] Instalando dependencias (requirements-build.txt)...
"%VENV_PY%" -m pip install -r requirements-build.txt
if errorlevel 1 goto :fail_pip

echo [3/5] Limpando build e dist...
if exist build rmdir /s /q build
if exist build goto :fail_clean
if exist dist rmdir /s /q dist
if exist dist goto :fail_clean

echo [4/5] Gerando o executavel com PyInstaller (%MODO%)...
rem O spec le ECO_ONEFILE; limpamos para nao herdar um valor antigo do ambiente.
set "ECO_ONEFILE="
if "%ONEFILE%"=="1" set "ECO_ONEFILE=1"
"%VENV_PY%" -m PyInstaller --noconfirm --clean EcoRunner.spec
if errorlevel 1 goto :fail_pyinstaller
if not exist "%EXE%" goto :fail_missing_exe

echo [5/5] Copiando README.md e executando o self-test...
copy /y "README.md" "%OUT_DIR%\" >nul
if errorlevel 1 goto :fail_copy

if exist "%REPORT%" del /q "%REPORT%"
set "SDL_VIDEODRIVER=dummy"
"%EXE%" --self-test 60
set "TEST_RC=%ERRORLEVEL%"
set "SDL_VIDEODRIVER="
if not "%TEST_RC%"=="0" goto :fail_selftest
if not exist "%REPORT%" goto :fail_selftest

echo.
echo Build concluido (%MODO%).
if "%ONEFILE%"=="1" (
    echo Distribua o arquivo: %CD%\%EXE%
) else (
    echo Distribua a pasta inteira: %CD%\%OUT_DIR%
    echo Executavel: %CD%\%EXE%
)
echo Relatorio do self-test: %REPORT%
goto :end

:fail_cd
echo ERRO: nao foi possivel entrar na pasta do script.
goto :fail

:fail_python
echo ERRO: Python 3 nao encontrado.
echo Instale em https://www.python.org/downloads/ marcando "Add python.exe to PATH".
goto :fail

:fail_venv
echo ERRO: falha ao criar o ambiente virtual .venv.
goto :fail

:fail_pip
echo ERRO: falha ao instalar as dependencias. Verifique a conexao com a internet.
goto :fail

:fail_clean
echo ERRO: nao foi possivel remover build ou dist. Feche programas que estejam usando esses arquivos.
goto :fail

:fail_pyinstaller
echo ERRO: o PyInstaller falhou. Veja as mensagens acima.
goto :fail

:fail_missing_exe
echo ERRO: executavel nao encontrado: %EXE%
goto :fail

:fail_copy
echo ERRO: nao foi possivel copiar README.md para %OUT_DIR%.
goto :fail

:fail_selftest
echo ERRO: o self-test falhou (codigo %TEST_RC%) ou nao gerou o relatorio em %REPORT%.
goto :fail

:fail
echo.
echo Build NAO concluido.
if "%NOPAUSE%"=="0" pause
endlocal
exit /b 1

:end
echo.
if "%NOPAUSE%"=="0" pause
endlocal
exit /b 0
