"""
Renderizador de modelos OBJ/MTL -> sprites PNG (RGBA) para o Eco Runner.

O Pygame é 2D, então os modelos 3D da pasta são pré-renderizados em vista 3/4
(mesmo estilo dos sprites Dieselpunk já existentes): projeção ortográfica,
textura difusa (map_Kd), cor Kd, emissão Ke e sombreamento Lambert por face.

Uso:
    python tools/render_models.py --models PASTA_MODELOS_3D [--only trees props trash]

Requer: numpy, Pillow (somente para gerar os sprites; o jogo não precisa).
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image

SPRITE_MAX = 368      # maior lado do sprite final (igual aos sprites existentes)
PADDING = 4
SUPERSAMPLE = 3


# -----------------------------------------------------------------------------
# Leitura OBJ / MTL
# -----------------------------------------------------------------------------

@dataclass
class Material:
    kd: Tuple[float, float, float] = (0.8, 0.8, 0.8)
    ke: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    texture: Optional[np.ndarray] = None  # HxWx3 float 0..1


@dataclass
class Mesh:
    vertices: np.ndarray
    uvs: np.ndarray
    tris: List[Tuple[Tuple[int, int, int], Tuple[int, int, int], str, str]] = field(default_factory=list)
    materials: Dict[str, Material] = field(default_factory=dict)


def load_texture(path: Path) -> Optional[np.ndarray]:
    try:
        return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0
    except OSError:
        return None


def parse_mtl(path: Path) -> Dict[str, Material]:
    mats: Dict[str, Material] = {}
    current: Optional[Material] = None
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.strip().split()
        if not parts or parts[0].startswith("#"):
            continue
        key = parts[0]
        if key == "newmtl":
            current = Material()
            mats[" ".join(parts[1:])] = current
        elif current is None:
            continue
        elif key == "Kd":
            current.kd = tuple(float(x) for x in parts[1:4])  # type: ignore
        elif key == "Ke":
            current.ke = tuple(float(x) for x in parts[1:4])  # type: ignore
        elif key == "map_Kd":
            current.texture = load_texture(path.parent / " ".join(parts[1:]))
    return mats


def parse_obj(path: Path, default_texture: Optional[Path] = None) -> Mesh:
    verts: List[List[float]] = []
    uvs: List[List[float]] = []
    tris = []
    materials: Dict[str, Material] = {}
    material = "__default__"
    group = ""
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.split()
        if not parts:
            continue
        key = parts[0]
        if key == "v":
            verts.append([float(x) for x in parts[1:4]])
        elif key == "vt":
            uvs.append([float(parts[1]), float(parts[2]) if len(parts) > 2 else 0.0])
        elif key == "mtllib":
            mtl = path.parent / " ".join(parts[1:])
            if mtl.is_file():
                materials.update(parse_mtl(mtl))
        elif key == "usemtl":
            material = " ".join(parts[1:])
        elif key == "g":
            group = " ".join(parts[1:])
        elif key == "f":
            refs = []
            for token in parts[1:]:
                pieces = token.split("/")
                vi = int(pieces[0])
                vi = vi - 1 if vi > 0 else len(verts) + vi
                ti = -1
                if len(pieces) > 1 and pieces[1]:
                    ti = int(pieces[1])
                    ti = ti - 1 if ti > 0 else len(uvs) + ti
                refs.append((vi, ti))
            for i in range(1, len(refs) - 1):
                a, b, c = refs[0], refs[i], refs[i + 1]
                tris.append(((a[0], b[0], c[0]), (a[1], b[1], c[1]), material, group))
    if "__default__" not in materials:
        tex = load_texture(default_texture) if default_texture else None
        materials["__default__"] = Material(kd=(1.0, 1.0, 1.0) if tex is not None else (0.7, 0.7, 0.7), texture=tex)
    return Mesh(np.array(verts, dtype=np.float64), np.array(uvs or [[0.0, 0.0]], dtype=np.float64), tris, materials)


# -----------------------------------------------------------------------------
# Rasterização
# -----------------------------------------------------------------------------

def rotation(yaw_deg: float, pitch_deg: float) -> np.ndarray:
    y, p = math.radians(yaw_deg), math.radians(pitch_deg)
    ry = np.array([[math.cos(y), 0, math.sin(y)], [0, 1, 0], [-math.sin(y), 0, math.cos(y)]])
    rx = np.array([[1, 0, 0], [0, math.cos(p), -math.sin(p)], [0, math.sin(p), math.cos(p)]])
    return rx @ ry


def render(
    mesh: Mesh,
    yaw: float = -35.0,
    pitch: float = 24.0,
    group_colors: Optional[Dict[str, Tuple[float, float, float]]] = None,
    sprite_max: int = SPRITE_MAX,
    light_dir: Tuple[float, float, float] = (-0.45, 0.75, 0.55),
    ambient: float = 0.42,
    gain: float = 1.0,
) -> Image.Image:
    rot = rotation(yaw, pitch)
    v = mesh.vertices @ rot.T              # espaço de câmera: x direita, y cima, z para o observador
    mn, mx = v.min(axis=0), v.max(axis=0)
    span = max(mx[0] - mn[0], mx[1] - mn[1]) or 1.0
    inner = (sprite_max - 2 * PADDING) * SUPERSAMPLE
    scale = inner / span
    w = int(math.ceil((mx[0] - mn[0]) * scale)) + 2 * PADDING * SUPERSAMPLE
    h = int(math.ceil((mx[1] - mn[1]) * scale)) + 2 * PADDING * SUPERSAMPLE
    sx = (v[:, 0] - mn[0]) * scale + PADDING * SUPERSAMPLE
    sy = (mx[1] - v[:, 1]) * scale + PADDING * SUPERSAMPLE
    sz = v[:, 2]

    color = np.zeros((h, w, 3), dtype=np.float32)
    mask = np.zeros((h, w), dtype=np.float32)
    zbuf = np.full((h, w), -np.inf, dtype=np.float64)
    light = np.array(light_dir, dtype=np.float64)
    light /= np.linalg.norm(light)

    for (ia, ib, ic), (ta, tb, tc), mat_name, group in mesh.tris:
        pa, pb, pc = v[ia], v[ib], v[ic]
        normal = np.cross(pb - pa, pc - pa)
        length = np.linalg.norm(normal)
        if length == 0:
            continue
        normal /= length
        if normal[2] < 0:                  # face de costas: usa normal invertida (malhas sem orientação garantida)
            normal = -normal
        shade = ambient + (1.0 - ambient) * max(0.0, float(normal @ light))

        xs = np.array([sx[ia], sx[ib], sx[ic]])
        ys = np.array([sy[ia], sy[ib], sy[ic]])
        x0, x1 = max(int(xs.min()), 0), min(int(xs.max()) + 1, w - 1)
        y0, y1 = max(int(ys.min()), 0), min(int(ys.max()) + 1, h - 1)
        if x0 > x1 or y0 > y1:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        denom = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(denom) < 1e-12:
            continue
        l0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / denom
        l1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / denom
        l2 = 1.0 - l0 - l1
        inside = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
        if not inside.any():
            continue
        depth = l0 * sz[ia] + l1 * sz[ib] + l2 * sz[ic]
        region = zbuf[y0:y1 + 1, x0:x1 + 1]
        visible = inside & (depth > region)
        if not visible.any():
            continue

        material = mesh.materials.get(mat_name) or mesh.materials["__default__"]
        kd = np.array(material.kd, dtype=np.float32)
        if group_colors is not None:
            kd = np.array(group_colors.get(group, group_colors.get("*", (0.8, 0.8, 0.8))), dtype=np.float32)
            base = np.broadcast_to(kd, visible.shape + (3,))
        elif material.texture is not None and min(ta, tb, tc) >= 0:
            tex = material.texture
            uv = mesh.uvs
            u = l0 * uv[ta, 0] + l1 * uv[tb, 0] + l2 * uv[tc, 0]
            vv = l0 * uv[ta, 1] + l1 * uv[tb, 1] + l2 * uv[tc, 1]
            th, tw = tex.shape[:2]
            px = (np.mod(u, 1.0) * (tw - 1)).astype(int)
            py = ((1.0 - np.mod(vv, 1.0)) * (th - 1)).astype(int)
            base = tex[py, px] * kd
        else:
            base = np.broadcast_to(kd, visible.shape + (3,))
        rgb = np.clip(base * shade * gain + np.array(material.ke, dtype=np.float32) * 0.6, 0.0, 1.0)

        region[visible] = depth[visible]
        color[y0:y1 + 1, x0:x1 + 1][visible] = rgb[visible]
        mask[y0:y1 + 1, x0:x1 + 1][visible] = 1.0

    # Reduz a supersamostragem com alfa pré-multiplicado (bordas suaves).
    out_w, out_h = max(1, w // SUPERSAMPLE), max(1, h // SUPERSAMPLE)
    premult = Image.fromarray((color * mask[..., None] * 255).astype(np.uint8), "RGB").resize((out_w, out_h), Image.LANCZOS)
    alpha = Image.fromarray((mask * 255).astype(np.uint8), "L").resize((out_w, out_h), Image.LANCZOS)
    a = np.asarray(alpha, dtype=np.float32) / 255.0
    rgb_out = np.asarray(premult, dtype=np.float32) / 255.0
    with np.errstate(divide="ignore", invalid="ignore"):
        rgb_out = np.where(a[..., None] > 0, rgb_out / np.maximum(a[..., None], 1e-6), 0.0)
    rgba = np.dstack([np.clip(rgb_out, 0, 1) * 255, a * 255]).astype(np.uint8)
    return Image.fromarray(rgba, "RGBA")


# -----------------------------------------------------------------------------
# Catálogo: qual modelo vira qual sprite do jogo
# -----------------------------------------------------------------------------

SOLARPUNK_TREES = [
    "01_art_nouveau_solar_tree", "02_carvalho_solar", "03_cipreste_fotovoltaico",
    "04_salgueiro_luminoso", "05_baoba_de_vidro", "06_pinheiro_vitral",
    "07_cerejeira_bioluminescente", "08_palmeira_solar", "09_bosque_bambu_solar",
    "10_arvore_cristalina",
]

DIESELPUNK_PROPS = {
    "fabrica": "01_fabrica_dieselpunk", "chamine": "02_chamine_de_fumaca",
    "caldeira": "03_caldeira_de_pressao", "tubos_valvula": "04_rede_de_tubos_com_valvula",
    "tambores": "05_tambores_de_oleo_enferrujados", "lixo": "06_monte_de_lixo_industrial",
    "sucata": "07_pilha_de_sucata_metalica", "cacamba": "08_cacamba_de_residuos",
}

TRASH_ITEMS = [
    "rusty_can", "chemical_battery", "radio_transceiver", "junkyard_mask",
    "shattered_spotlight", "turbine_debris", "broken_pipe", "scrap_heap",
    "piston_pump", "debris_plate",
]

# Kit "Dieselpunk_Scenario" (modelos_3d/Dieselpunk_Scenario/assets/models):
# nome do sprite -> caminho do OBJ dentro de assets/models.
SCENARIO_MODELS = {
    "background_silo": "background/DP_Background_Silo",
    "distant_factory": "background/DP_Distant_Factory",
    "power_pylon": "background/DP_Power_Pylon",
    "metal_bridge": "bridges/DP_Metal_Bridge",
    "factory_roof_a": "factories/DP_Factory_Roof_A",
    "factory_wall_a": "factories/DP_Factory_Wall_A",
    "factory_wall_b": "factories/DP_Factory_Wall_B",
    "boiler_compressor": "machines/DP_Boiler_Compressor",
    "diesel_generator": "machines/DP_Diesel_Generator",
    "industrial_chimney": "machines/DP_Industrial_Chimney",
    "industrial_fan": "machines/DP_Industrial_Fan",
    "pressure_tank": "machines/DP_Pressure_Tank",
    "steam_pipe_corner": "pipes/DP_Steam_Pipe_Corner",
    "steam_pipe_straight": "pipes/DP_Steam_Pipe_Straight",
    "steam_pipe_tee": "pipes/DP_Steam_Pipe_Tee",
    "valve_manifold": "pipes/DP_Valve_Manifold",
    "cargo_elevator": "platforms/DP_Cargo_Elevator",
    "fixed_crane": "platforms/DP_Fixed_Crane",
    "industrial_stairs": "platforms/DP_Industrial_Stairs",
    "metal_walkway": "platforms/DP_Metal_Walkway",
    "amber_light": "props/DP_Amber_Light",
    "cable_reel": "props/DP_Cable_Reel",
    "control_panel": "props/DP_Control_Panel",
    "fuel_barrel": "props/DP_Fuel_Barrel",
    "rusted_crate": "props/DP_Rusted_Crate",
    "hangar_door_a": "structures/DP_Hangar_Door_A",
    "metal_support": "structures/DP_Metal_Support",
    "industrial_tower_a": "towers/DP_Industrial_Tower_A",
}

# Silhuetas do horizonte (camada distante): vista quase frontal.
SKYLINE_MODELS = [
    "background_silo", "distant_factory", "power_pylon", "industrial_tower_a",
    "industrial_chimney", "fixed_crane", "pressure_tank", "cargo_elevator",
]

# Texturas de atmosfera copiadas do kit: arquivo de origem -> nome no jogo.
ATMOSPHERE_TEXTURES = {
    "Emission/DP_Polluted_Sky_Panorama.png": "sky_panorama.png",
    "Industrial/DP_Toxic_Smog_Cloud.png": "smog_cloud.png",
}



def save(img: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, optimize=True)
    print(f"  {path.relative_to(path.parents[2]) if len(path.parents) > 2 else path}  {img.size}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", type=Path, required=True, help="pasta modelos_3d (OBJ/MTL/textures)")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "assets")
    parser.add_argument("--only", nargs="*",
                        help="renderiza só estes grupos: trees props trash scenario")
    parser.add_argument("--scenario", type=Path, default=None,
                        help="pasta do kit Dieselpunk_Scenario (padrão: MODELS/Dieselpunk_Scenario)")
    args = parser.parse_args()
    groups = set(args.only or ["trees", "props", "trash", "scenario"])
    junk_texture = args.models / "texturas" / "textura_rusty_scrap_dieselpunk.jpg"

    if "trees" in groups:
        print("Árvores Solarpunk:")
        for name in SOLARPUNK_TREES:
            save(render(parse_obj(args.models / f"{name}.obj")), args.out / "solarpunk_sprites" / f"{name}.png")
    if "props" in groups:
        print("Props Dieselpunk:")
        for sprite, name in DIESELPUNK_PROPS.items():
            save(render(parse_obj(args.models / f"{name}.obj")), args.out / "dieselpunk_sprites" / f"{sprite}.png")
    if "trash" in groups:
        print("Lixo coletável:")
        for name in TRASH_ITEMS:
            mesh = parse_obj(args.models / f"{name}.obj", default_texture=junk_texture)
            save(render(mesh, yaw=-30, pitch=28, sprite_max=256), args.out / "trash_sprites" / f"{name}.png")
    if "scenario" in groups:
        kit = args.scenario or (args.models / "Dieselpunk_Scenario")
        models_dir = kit / "assets" / "models"
        if not models_dir.is_dir():
            print(f"Kit Dieselpunk_Scenario não encontrado em {kit}; grupo 'scenario' ignorado.")
            return
        print("Cenário (kit Dieselpunk_Scenario):")
        for sprite, rel in SCENARIO_MODELS.items():
            mesh = parse_obj(models_dir / f"{rel}.obj")
            # Os materiais do kit são escuros: mais luz ambiente e ganho para ler bem no jogo.
            save(render(mesh, ambient=0.5, gain=1.45, sprite_max=320), args.out / "scenario_sprites" / f"{sprite}.png")
        print("Silhuetas do horizonte:")
        for sprite in SKYLINE_MODELS:
            mesh = parse_obj(models_dir / f"{SCENARIO_MODELS[sprite]}.obj")
            save(render(mesh, yaw=-18, pitch=6, ambient=0.5, gain=1.3, sprite_max=256),
                 args.out / "skyline_sprites" / f"{sprite}.png")
        print("Atmosfera:")
        for source, target in ATMOSPHERE_TEXTURES.items():
            img = Image.open(kit / "assets" / "textures" / source).convert("RGBA")
            save(img, args.out / "atmosphere" / target)


if __name__ == "__main__":
    main()
