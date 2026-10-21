# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec do Eco Runner.
#
# Uso:
#   pyinstaller --noconfirm --clean EcoRunner.spec            (modo --onedir, padrão)
#   ECO_ONEFILE=1 pyinstaller --noconfirm --clean EcoRunner.spec   (modo --onefile)
#   ECO_CONSOLE=1 ...  mantém a janela de console (útil para depuração)
#
# Os assets são opcionais: só entram no pacote as pastas que existirem.

import os
from pathlib import Path

ROOT = Path(SPECPATH).resolve()
ONEFILE = os.environ.get("ECO_ONEFILE") == "1"
CONSOLE = os.environ.get("ECO_CONSOLE") == "1"

ASSET_EXTS = {".png", ".json", ".obj", ".mtl", ".jpg", ".jpeg", ".task"}
OPTIONAL_DIRS = [
    "dieselpunk_sprites", "powerup_sprites", "powerup_models",
    "solarpunk_sprites", "trash_sprites", "plane_sprites", "plane_menu",
    "scenario_sprites", "skyline_sprites", "atmosphere", "ground",
    "plane_paint", "plane_menu_paint", "plane_uv", "plane_menu_uv",
    "plane_patterns", "maneuvers", "pose_model", "era_final_sprites", "era_final_fx",
]

datas = []
for name in OPTIONAL_DIRS:
    for base in (ROOT / "assets" / name, ROOT / name):
        if not base.is_dir():
            continue
        for file in base.rglob("*"):
            if file.is_file() and file.suffix.lower() in ASSET_EXTS:
                rel_parent = file.parent.relative_to(base)
                dest = Path("assets") / name / rel_parent
                datas.append((str(file), str(dest)))
        break  # usa a primeira pasta encontrada (assets/ tem prioridade)

icon = None
for candidate in (ROOT / "assets" / "icon.ico", ROOT / "icon.ico"):
    if candidate.is_file():
        icon = str(candidate)
        break

a = Analysis(
    [str(ROOT / "eco_runner.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "unittest", "pydoc", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="EcoRunner",
        debug=False,
        strip=False,
        upx=False,
        runtime_tmpdir=None,
        console=CONSOLE,
        icon=icon,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="EcoRunner",
        debug=False,
        strip=False,
        upx=False,
        console=CONSOLE,
        icon=icon,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="EcoRunner",
    )
