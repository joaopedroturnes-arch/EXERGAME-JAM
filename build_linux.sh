#!/usr/bin/env bash
# build_linux.sh - gera o executavel Linux do Eco Runner com PyInstaller (onedir).
#
# Uso:
#   ./build_linux.sh
#   Saida: dist/EcoRunner/EcoRunner (distribua a pasta dist/EcoRunner inteira).
#
# Assets: o EcoRunner.spec ja empacota assets/ no executavel. Por isso assets/
# NAO e copiado para dist/EcoRunner/. O jogo tambem procura assets/ ao lado do
# executavel, antes do pacote: para trocar um sprite sem recompilar, basta
# colocar o PNG em dist/EcoRunner/assets/<pasta>/<nome>.png.
#
# O PyInstaller nao faz compilacao cruzada: o .exe do Windows deve ser gerado
# no Windows (build_windows.bat).
set -euo pipefail

die() {
    echo "ERRO: $*" >&2
    exit 1
}

cd "$(dirname "${BASH_SOURCE[0]}")"

APP_DIR="dist/EcoRunner"
EXE="$APP_DIR/EcoRunner"

command -v python3 >/dev/null 2>&1 \
    || die "python3 nao encontrado (no Debian/Ubuntu: sudo apt install python3 python3-venv)."

echo "[1/5] Preparando o ambiente virtual .venv..."
if [ ! -x ".venv/bin/python" ]; then
    python3 -m venv .venv \
        || die "falha ao criar .venv (no Debian/Ubuntu instale o pacote python3-venv)."
fi
PY=".venv/bin/python"

echo "[2/5] Instalando dependencias (requirements-build.txt)..."
"$PY" -m pip install -r requirements-build.txt \
    || die "falha ao instalar as dependencias. Verifique a conexao com a internet."

echo "[3/5] Limpando build/ e dist/..."
rm -rf build dist

echo "[4/5] Gerando o executavel com PyInstaller..."
"$PY" -m PyInstaller --noconfirm --clean EcoRunner.spec \
    || die "o PyInstaller falhou. Veja as mensagens acima."
[ -x "$EXE" ] || die "executavel nao encontrado: $EXE"

echo "[5/5] Copiando README.md e executando o self-test..."
cp README.md "$APP_DIR/" || die "nao foi possivel copiar README.md para $APP_DIR/."

# Pasta de dados do jogo (ver user_data_dir no eco_runner.py).
DATA_DIR="${ECO_RUNNER_DATA_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/EcoRunner}"
REPORT="$DATA_DIR/self_test.json"
rm -f "$REPORT"

if ! SDL_VIDEODRIVER=dummy "$EXE" --self-test 60; then
    die "o self-test falhou (codigo de saida diferente de 0)."
fi
[ -f "$REPORT" ] || die "o self-test nao gerou o relatorio em $REPORT."
grep -q '"status": "ok"' "$REPORT" || die "relatorio do self-test sem status ok: $REPORT"

echo ""
echo "Build concluido com sucesso."
echo "Executavel: $(pwd)/$EXE"
echo "Relatorio do self-test: $REPORT"
