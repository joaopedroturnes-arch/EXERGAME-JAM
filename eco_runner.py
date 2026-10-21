"""
Eco Runner + Gerador de Modelos 3D Solarpunk Art Nouveau
-------------------------------------------------------
Este arquivo contém:
1. Um gerador procedural de arquivos 3D (.OBJ / .MTL) para Árvores Solarpunk.
2. O jogo Pygame em projeção pseudo-3D: o jogador pilota um AVIÃO DE PAPEL
   (11 modelos do "Estúdio 3D Aviões, 14-Bis & Piloto") em todas as direções.
   O boneco em cima do avião é uma customização opcional (7 opções de piloto).
3. Cenário, lixo e obstáculos feitos a partir dos modelos 3D da pasta
   (props Dieselpunk, árvores Solarpunk e sucata), pré-renderizados em sprites.
4. Sistema de 3 vidas, invulnerabilidade, escudo, ímã de coleta e reparo.
5. Recorde e avião escolhido salvos localmente (JSON).

Instalação e execução:
    pip install pygame
    python eco_runner.py

Hangar (tela inicial):
    ←/→ ou A/D: trocar avião     ↑/↓ ou W/S: trocar piloto     ENTER/ESPAÇO: decolar

Voo:
    ←/→ ou A/D: ir para os lados
    ↑, W ou espaço: subir         ↓ ou S: descer
    P/ESC: pausar (C na pausa: voltar ao hangar)
    F3: mostrar hitboxes
    ENTER/ESPAÇO após game over: voar de novo   |   C: voltar ao hangar

Obstáculos:
    Tambores, caçamba, sucata e monte de lixo: voe POR CIMA
    Rede de tubos com válvula: passe POR BAIXO
    Chaminé e caldeira: desvie PARA O LADO

Power-ups:
    Escudo: protege contra colisões por 6 segundos
    Ímã: coleta lixo nas faixas vizinhas por 7 segundos
    Reparo: recupera uma vida ou aumenta a restauração

Para gerar a árvore .OBJ do exportador, execute:
    python eco_runner.py --generate-3d [--output-dir PASTA]

Opções extras (não alteram a jogabilidade):
    --self-test [N]   roda N quadros sem interação e grava um relatório JSON
                      (útil para validar o executável empacotado)

Caminhos (compatível com Python e com PyInstaller):
    Assets  -> procurados em assets/<pasta>/ ou <pasta>/ ao lado do executável
               ou do script e, por fim, dentro do pacote do PyInstaller.
    Recorde -> executável: %APPDATA%/EcoRunner (Windows) ou
               ~/.local/share/EcoRunner (Linux); via Python: save/ do projeto.
"""

from __future__ import annotations

import math
import random
import sys
import os
import json
import tempfile
import time
import traceback
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

from webcam_control import PoseCameraSource, WebcamControl  # noqa: E402

APP_NAME = "EcoRunner"
SAVE_FILENAME = "eco_runner_recorde.json"
TREE_OBJ_FILENAME = "solarpunk_tree_alphonse.obj"

# -----------------------------------------------------------------------------
# CAMINHOS: execução direta (python eco_runner.py) ou empacotada (PyInstaller)
# -----------------------------------------------------------------------------

def is_frozen() -> bool:
    """True quando o jogo roda a partir do executável do PyInstaller."""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Pasta do executável (empacotado) ou do script (Python)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundle_dir() -> Path:
    """Pasta dos arquivos embutidos (sys._MEIPASS no PyInstaller)."""
    meipass = getattr(sys, "_MEIPASS", None)
    return Path(meipass) if meipass else app_dir()


def asset_dir_candidates(name: str) -> List[Path]:
    """Ordem de busca de uma pasta de assets opcional.

    Pastas ao lado do executável vêm primeiro, para que o jogador possa
    adicionar ou trocar sprites sem recompilar.
    """
    candidates: List[Path] = []
    for base in (app_dir(), bundle_dir()):
        for path in (base / "assets" / name, base / name):
            if path not in candidates:
                candidates.append(path)
    return candidates


def find_asset_dir(name: str) -> Optional[Path]:
    for path in asset_dir_candidates(name):
        if path.is_dir():
            return path
    return None


def find_pose_model() -> Optional[Path]:
    """Modelo do MediaPipe Pose (pasta assets/pose_model), ou None se faltar."""
    for folder in asset_dir_candidates("pose_model"):
        path = folder / POSE_MODEL_NAME
        if path.is_file():
            return path
    return None


def _platform_user_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


_DATA_DIR_CACHE: Optional[Path] = None


def user_data_dir() -> Path:
    """Pasta gravável para recorde, logs e modelos gerados.

    Ordem: variável ECO_RUNNER_DATA_DIR (testes) -> pasta do sistema (versão
    empacotada) ou save/ do projeto (versão Python) -> pasta do sistema ->
    pasta temporária. Nunca grava dentro do pacote somente leitura.
    """
    global _DATA_DIR_CACHE
    if _DATA_DIR_CACHE is not None:
        return _DATA_DIR_CACHE
    candidates: List[Path] = []
    override = os.environ.get("ECO_RUNNER_DATA_DIR")
    if override:
        candidates.append(Path(override))
    if is_frozen():
        candidates.append(_platform_user_data_dir())
    else:
        candidates.append(app_dir() / "save")
        candidates.append(_platform_user_data_dir())
    candidates.append(Path(tempfile.gettempdir()) / APP_NAME)
    for path in candidates:
        if _is_writable_dir(path):
            _DATA_DIR_CACHE = path
            return path
    _DATA_DIR_CACHE = candidates[-1]
    return _DATA_DIR_CACHE


def save_file_path() -> Path:
    return user_data_dir() / SAVE_FILENAME


def legacy_save_paths() -> List[Path]:
    """Locais antigos do recorde (ao lado do script), lidos para migração."""
    return [app_dir() / SAVE_FILENAME]


def _read_record(path: Path) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return max(0, int(data.get("recorde", 0)))
    except (OSError, ValueError, TypeError, AttributeError):
        return 0


def show_message(title: str, text: str) -> None:
    """Mostra uma mensagem simples ao usuário (sem traceback)."""
    if sys.platform.startswith("win"):
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)
            return
        except Exception:
            pass
    stream = sys.stderr or sys.stdout
    if stream is not None:
        try:
            print(f"{title}: {text}", file=stream)
        except Exception:
            pass

# -----------------------------------------------------------------------------
# MÓDULO GERADOR DE MODELOS 3D (.OBJ / .MTL)
# -----------------------------------------------------------------------------

@dataclass
class Mesh3D:
    name: str
    vertices: List[Tuple[float, float, float]] = field(default_factory=list)
    normals: List[Tuple[float, float, float]] = field(default_factory=list)
    uvs: List[Tuple[float, float]] = field(default_factory=list)
    faces: List[List[Tuple[int, int, int]]] = field(default_factory=list) # v, uv, n

def create_cylinder_mesh(
    base_center: Tuple[float, float, float],
    radius_bottom: float,
    radius_top: float,
    height: float,
    segments: int = 12,
    curve_offset: Tuple[float, float] = (0.0, 0.0)
) -> Mesh3D:
    """Gera uma seção cilíndrica de tronco curvo com UVs e normais radiais."""
    mesh = Mesh3D("TrunkSection")
    bx, by, bz = base_center
    cx, cz = curve_offset

    # Anel Inferior
    for i in range(segments):
        angle = (2 * math.pi * i) / segments
        vx = bx + radius_bottom * math.cos(angle)
        vy = by
        vz = bz + radius_bottom * math.sin(angle)
        mesh.vertices.append((vx, vy, vz))
        mesh.uvs.append((i / segments, 0.0))
        mesh.normals.append((math.cos(angle), 0.0, math.sin(angle)))

    # Anel Superior
    for i in range(segments):
        angle = (2 * math.pi * i) / segments
        vx = bx + cx + radius_top * math.cos(angle)
        vy = by + height
        vz = bz + cz + radius_top * math.sin(angle)
        mesh.vertices.append((vx, vy, vz))
        mesh.uvs.append((i / segments, 1.0))
        mesh.normals.append((math.cos(angle), 0.0, math.sin(angle)))

    # Faces quadriláteras (divididas em triângulos)
    for i in range(segments):
        nxt = (i + 1) % segments
        v1 = i + 1
        v2 = nxt + 1
        v3 = nxt + 1 + segments
        v4 = i + 1 + segments

        # Quad -> 2 Triângulos
        mesh.faces.append([(v1, v1, v1), (v2, v2, v2), (v3, v3, v3)])
        mesh.faces.append([(v1, v1, v1), (v3, v3, v3), (v4, v4, v4)])

    return mesh

def default_3d_output_dir() -> Path:
    """Executável: pasta de dados do usuário; Python: modelos_3d/ do projeto."""
    if is_frozen():
        return user_data_dir() / "modelos_3d"
    return app_dir() / "modelos_3d"


def export_solarpunk_tree_obj(
    filename: str = TREE_OBJ_FILENAME, output_dir: Optional[Path] = None
) -> Tuple[Path, Path]:
    """Gera o arquivo OBJ/MTL completo da Árvore Fotovoltaica Art Nouveau."""
    obj_path = Path(filename)
    if not obj_path.is_absolute():
        obj_path = Path(output_dir or default_3d_output_dir()) / obj_path
    obj_path.parent.mkdir(parents=True, exist_ok=True)
    mtl_path = obj_path.with_suffix(".mtl")
    filename = str(obj_path)
    mtl_filename = str(mtl_path)

    # Criar tronco em curva "S" (Art Nouveau)
    segments = 16
    height_steps = 6
    curr_y = 0.0
    radius = 0.8
    
    total_v = 0
    total_uv = 0
    total_n = 0
    current_x = 0.0
    current_z = 0.0
    
    with open(filename, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Árvore Solarpunk Art Nouveau OBJ Exporter\n")
        # Nome relativo: o .mtl fica sempre ao lado do .obj.
        f.write(f"mtllib {mtl_path.name}\n")
        
        # Gerar Nós da Árvore
        for step in range(height_steps):
            h = 1.5
            curve_x = math.sin(step * 0.8) * 0.6
            curve_z = math.cos(step * 0.8) * 0.3
            next_radius = radius * 0.82
            
            mesh = create_cylinder_mesh(
                (current_x, curr_y, current_z),
                radius,
                next_radius,
                h,
                segments,
                (curve_x, curve_z),
            )
            
            # Escrever vértices
            f.write(f"g Trunk_Section_{step}\n")
            f.write("usemtl Solarpunk_Wood\n")
            for v in mesh.vertices:
                f.write(f"v {v[0]:.4f} {v[1]:.4f} {v[2]:.4f}\n")
            for uv in mesh.uvs:
                f.write(f"vt {uv[0]:.4f} {uv[1]:.4f}\n")
            for normal in mesh.normals:
                f.write(f"vn {normal[0]:.4f} {normal[1]:.4f} {normal[2]:.4f}\n")
            
            for face in mesh.faces:
                refs = [
                    f"{vertex + total_v}/{uv + total_uv}/{normal + total_n}"
                    for vertex, uv, normal in face
                ]
                f.write(f"f {' '.join(refs)}\n")
                
            total_v += len(mesh.vertices)
            total_uv += len(mesh.uvs)
            total_n += len(mesh.normals)
            curr_y += h
            current_x += curve_x
            current_z += curve_z
            radius = next_radius

        # Gerar Copa Folhar Solarpunk (Painéis de Vitral Hexagonais)
        f.write("g Solar_Canopy\n")
        f.write("usemtl Solarpunk_Glass_Panel\n")
        
        canopy_y = curr_y + 0.5
        canopy_sides = 6
        canopy_radius = 3.2
        
        # Centro da Copa (alinhado ao topo do tronco curvo)
        f.write(f"v {current_x:.4f} {canopy_y + 1.2:.4f} {current_z:.4f}\n")
        center_idx = total_v + 1
        total_v += 1

        # Anel de painéis
        for i in range(canopy_sides):
            angle = (2 * math.pi * i) / canopy_sides
            px = current_x + canopy_radius * math.cos(angle)
            pz = current_z + canopy_radius * math.sin(angle)
            py = canopy_y + (0.3 if i % 2 == 0 else -0.3)
            f.write(f"v {px:.4f} {py:.4f} {pz:.4f}\n")
        
        for i in range(canopy_sides):
            nxt = (i + 1) % canopy_sides
            p1 = center_idx
            p2 = center_idx + 1 + i
            p3 = center_idx + 1 + nxt
            f.write(f"f {p1} {p2} {p3}\n")

    # Arquivo Material (.MTL)
    with open(mtl_filename, "w", encoding="utf-8", newline="\n") as f:
        f.write("# Materiais Solarpunk\n\n")
        f.write("newmtl Solarpunk_Wood\n")
        f.write("Kd 0.55 0.42 0.35\n") # Cor de madeira bronzeada
        f.write("Ks 0.3 0.3 0.3\n")
        f.write("Ns 20.0\n\n")
        
        f.write("newmtl Solarpunk_Glass_Panel\n")
        f.write("Kd 0.0 0.9 0.45\n") # Verde Esmeralda
        f.write("Ke 0.1 0.8 0.4\n") # Emissão Suave
        f.write("Ks 0.9 0.9 0.9\n")
        f.write("d 0.85\n") # Transparência
        f.write("Ns 90.0\n")

    if sys.stdout is not None:
        print(f"[3D Exporter] Modelo gerado: {filename} e {mtl_filename}")
    return obj_path, mtl_path


# -----------------------------------------------------------------------------
# JOGO ECO RUNNER COM RENDERIZAÇÃO DAS ÁRVORES SOLARPUNK
# -----------------------------------------------------------------------------

WIDTH, HEIGHT = 1100, 650
FPS = 60
HORIZON_Y = 215
PLAYER_Z = 190.0
ROAD_WIDTH = 760.0
LANE_WIDTH = 220.0
FOV = 360.0

# Parâmetros ajustáveis do voo.
BASE_SPEED = 460.0             # antes 560: menos fluxo para frente na tela
# Teste da causa 3 (fluxo para frente dominante): o ganho de velocidade vindo da
# restauração e da dificuldade foi reduzido. Valores originais: 560, 1.8 e 80.0.
RESTORATION_SPEED_GAIN = 0.6
DIFFICULTY_SPEED_GAIN = 50.0
MAX_DT = 0.05
MAX_LATERAL_SPEED = 620.0      # unidades/s para os lados
MAX_VERTICAL_SPEED = 420.0     # unidades/s para cima/baixo
FLIGHT_RESPONSE = 9.0          # quão rápido o avião responde aos comandos
MIN_ALTITUDE = 22.0
MAX_ALTITUDE = 155.0         # acima disso o avião ficaria sob o HUD
START_ALTITUDE = 60.0
MAX_PLAYER_X = LANE_WIDTH          # mantém o avião inteiro na tela
MAX_ROLL_DEG = 26.0
PLANE_WIDTH = 130.0            # envergadura visual/colisão (mundo)
PLANE_HEIGHT = 34.0
HIGH_SCORE_SAVE_INTERVAL = 5.0
CONFIG_FILENAME = "eco_runner_config.json"
CONTROL_MODES = ("teclado", "camera", "mao")   # teclado, corpo pela webcam ou uma mão pela webcam
CONTROL_LABELS = {"teclado": "teclado", "camera": "corpo", "mao": "uma mão"}
CHEAT_CODE = (pygame.K_UP, pygame.K_UP, pygame.K_DOWN, pygame.K_DOWN, pygame.K_LEFT,
              pygame.K_RIGHT, pygame.K_LEFT, pygame.K_RIGHT, pygame.K_b, pygame.K_a)
CHEAT_FLASH_TIME = 0.35
POSE_MODEL_NAME = "pose_landmarker_lite.task"
NEAR_CLIP_Z = 60.0             # sprites mais perto que isso não são desenhados
# Teste de paralaxe: fração do deslocamento lateral do avião que a câmera acompanha.
# 0.0 = câmera fixa (comportamento anterior); 0.35 = o cenário desliza em relação ao avião.
CAMERA_FOLLOW = 0.35
# Paralaxe em camadas (o avião é o referencial da câmera). Do fundo para a frente:
#   céu      (panorama e sol):                SKY_SHIFT_PX por unidade + deriva SKY_DRIFT_PX;
#   nuvens   (fumaça / nuvens limpas):        CLOUD_SHIFT_PX, entre o céu e o horizonte;
#   distante (silhuetas do horizonte):        FAR_SHIFT_PX + deriva FAR_DRIFT_PX
#                                             (a fileira de trás anda FAR_BACK_RATIO disso);
#   média    (fileira de fundo das margens):  MID_PARALLAX × deslocamento da câmera;
#   borda    (fileira junto à pista):         MARGIN_PARALLAX × deslocamento da câmera;
#   próxima  (pista, obstáculos, avião):      câmera inteira (CAMERA_FOLLOW).
SKY_SHIFT_PX = 0.08
SKY_DRIFT_PX = 0.004
CLOUD_SHIFT_PX = 0.15
FAR_SHIFT_PX = 0.25
FAR_DRIFT_PX = 0.03
FAR_BACK_RATIO = 0.55
# Quanto cada faixa de silhuetas se mistura à neblina (mais longe = mais apagada).
SKYLINE_HAZE = {"back": 0.72, "front": 0.5, "trees": 0.45}
MID_PARALLAX = 0.5
MARGIN_PARALLAX = 0.8
# Fileiras das margens: distância lateral do centro da pista (unidades do mundo).
MARGIN_X = 480.0
MID_ROW_X = 690.0
MARGIN_MAX_Z = 1800.0          # além disso a fileira da borda fica pequena demais para aparecer
# Neblina: pista e objetos se misturam à cor do horizonte com a distância,
# então surgem aos poucos em vez de "brotar" no fim da pista.
FOG_START = 900.0
FOG_END = 2450.0
FOG_LEVELS = 10
# Grama no chão (eras III e IV): começa onde as árvores aparecem.
CAMERA_HEIGHT = 155.0          # altura da câmera usada em project()
GRASS_TILE_X = 240.0           # largura (mundo) que uma repetição da textura de grama cobre
GRASS_TILE_Z = 120.0           # profundidade (mundo) de uma repetição da textura de grama
GRASS_START_RESTORATION = 50.0 # mesma restauração em que as árvores passam a aparecer
GRASS_FALLBACK = ((74, 140, 52), (64, 128, 46))  # cores lisas se a textura faltar
# Concreto sujo no chão das áreas ainda não restauradas (toda a fase inicial).
CONCRETE_TILE_X = 400.0        # largura (mundo) de uma repetição da textura de concreto
CONCRETE_TILE_Z = 200.0        # profundidade (mundo): duas placas de 100 = um trecho da pista
CONCRETE_JOINTS_X = (560.0, 860.0, 1200.0)   # juntas paralelas à pista (dos dois lados)
CONCRETE_JOINT_COLOR = (46, 42, 38)
GROUND_ROW_GROUP = 1.06        # linhas de escala parecida compartilham a mesma textura reduzida
GROUND_STRIP_MIN = 560         # largura mínima (px) das faixas de textura guardadas
GROUND_TILES = {"grass": (GRASS_TILE_X, GRASS_TILE_Z), "concrete": (CONCRETE_TILE_X, CONCRETE_TILE_Z)}
# Céu poluído (panorama do kit) some conforme a restauração passa destes valores.
POLLUTION_CLEAR_START = 20.0
POLLUTION_CLEAR_END = 65.0
SKY_PANORAMA_SCALE = 1.4       # escala do panorama 1024x512 do kit
SKYLINE_HEIGHT = 160           # altura (px) das faixas de silhuetas do horizonte
SKYLINE_CHUNK = 220            # largura dos pedaços ao refazer as silhuetas
SKYLINE_BUDGET_MS = 1.5        # tempo máximo por quadro para refazer silhuetas
CLOUD_TILE = 1900              # ciclo horizontal das nuvens (px)
SPRITE_CACHE_LIMIT = 1400      # sprites reescalados guardados (descarte gradual)
DT_SMOOTHING = 0.25            # suavização do passo de tempo (menos tremor no movimento)
FAR_TILE = 2 * 1100            # largura do ciclo das silhuetas distantes (px)
FAR_STEP = 8
# Silhueta de reserva do horizonte (sem sprites): soma de senoides de frequência inteira.
FAR_PROFILE = [
    26 + 14 * abs(math.sin(2 * math.pi * 3 * (i * FAR_STEP) / FAR_TILE))
       + 10 * math.sin(2 * math.pi * 7 * (i * FAR_STEP) / FAR_TILE + 1.1)
       + 6 * math.sin(2 * math.pi * 13 * (i * FAR_STEP) / FAR_TILE + 0.4)
    for i in range(FAR_TILE // FAR_STEP)
]

# Alturas em que o lixo aparece (rasante, meia altura, alto).
TRASH_HEIGHTS = (32.0, 88.0, 140.0)

Color = Tuple[int, int, int]

def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * clamp(t, 0.0, 1.0)

def lerp_color(a: Color, b: Color, t: float) -> Color:
    t = clamp(t, 0.0, 1.0)
    return tuple(round(lerp(a[i], b[i], t)) for i in range(3))  # type: ignore

def rgb(hex_color: str) -> Color:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore

@dataclass(frozen=True)
class Stage:
    stage_id: str
    name: str
    min_value: float
    sky_top: Color
    sky_horizon: Color
    water: Color
    road_even: Color
    road_odd: Color
    lane_line: Color
    accent: Color

STAGES = [
    Stage("DIESELPUNK", "Era I: Dieselpunk Industrial", 0, rgb("1c1613"), rgb("4a3222"), rgb("261e18"), rgb("2b2623"), rgb("211d1a"), rgb("8d5b32"), rgb("ff7043")),
    Stage("CYBER_POLLUTION", "Era II: Poluição Corporativa", 25, rgb("101224"), rgb("311b38"), rgb("1a1c29"), rgb("252734"), rgb("1e202b"), rgb("ab47bc"), rgb("e040fb")),
    Stage("ECO_TRANSITION", "Era III: Despertar Ecológico", 50, rgb("1e88e5"), rgb("dce775"), rgb("26c6da"), rgb("795548"), rgb("6d4c41"), rgb("66bb6a"), rgb("69f0ae")),
    Stage("SOLARPUNK_NOUVEAU", "Era IV: Solarpunk Art Nouveau", 75, rgb("29b6f6"), rgb("fff59d"), rgb("00acc1"), rgb("a1887f"), rgb("8d6e63"), rgb("ffd54f"), rgb("ffd54f")),
]

# Props das margens nas eras I e II (modelos 01–08 de modelos_3d), em ordem fixa.
DIESELPUNK_PROP_SPECS: List[Tuple[str, float]] = [
    ("fabrica", 250.0),
    ("chamine", 310.0),
    ("caldeira", 190.0),
    ("tubos_valvula", 190.0),
    ("tambores", 165.0),
    ("lixo", 125.0),
    ("sucata", 145.0),
    ("cacamba", 155.0),
]

# Árvores das margens nas eras III e IV (modelos 01–10 Solarpunk), em ordem fixa.
SOLARPUNK_TREE_SPECS: List[Tuple[str, float]] = [
    ("01_art_nouveau_solar_tree", 300.0),
    ("02_carvalho_solar", 290.0),
    ("03_cipreste_fotovoltaico", 360.0),
    ("04_salgueiro_luminoso", 280.0),
    ("05_baoba_de_vidro", 300.0),
    ("06_pinheiro_vitral", 340.0),
    ("07_cerejeira_bioluminescente", 290.0),
    ("08_palmeira_solar", 330.0),
    ("09_bosque_bambu_solar", 320.0),
    ("10_arvore_cristalina", 310.0),
]

# Kit Dieselpunk_Scenario (modelos_3d/Dieselpunk_Scenario), renderizado em
# assets/scenario_sprites. Todas as listas abaixo seguem ordem fixa, sem sorteio.
SCENARIO_SPRITES = [
    "background_silo", "distant_factory", "power_pylon", "metal_bridge", "factory_roof_a",
    "factory_wall_a", "factory_wall_b", "boiler_compressor", "diesel_generator",
    "industrial_chimney", "industrial_fan", "pressure_tank", "steam_pipe_corner",
    "steam_pipe_straight", "steam_pipe_tee", "valve_manifold", "cargo_elevator",
    "fixed_crane", "industrial_stairs", "metal_walkway", "amber_light", "cable_reel",
    "control_panel", "fuel_barrel", "rusted_crate", "hangar_door_a", "metal_support",
    "industrial_tower_a",
]

# Fileira junto à pista (eras I e II): peças pequenas do kit.
MARGIN_PROP_SPECS: List[Tuple[str, float]] = [
    ("fuel_barrel", 62.0), ("valve_manifold", 88.0), ("rusted_crate", 52.0),
    ("cable_reel", 78.0), ("steam_pipe_straight", 58.0), ("control_panel", 92.0),
    ("diesel_generator", 82.0), ("amber_light", 48.0), ("steam_pipe_tee", 74.0),
    ("boiler_compressor", 96.0), ("steam_pipe_corner", 76.0), ("metal_walkway", 56.0),
]

# Fileira de fundo das margens (eras I e II): estruturas do kit intercaladas
# com os 8 props Dieselpunk originais.
MID_ROW_SPECS: List[Tuple[str, float]] = [
    ("industrial_tower_a", 400.0), ("fabrica", 250.0), ("pressure_tank", 200.0),
    ("factory_wall_a", 190.0), ("chamine", 310.0), ("fixed_crane", 360.0),
    ("cargo_elevator", 200.0), ("caldeira", 190.0), ("industrial_chimney", 320.0),
    ("factory_wall_b", 190.0), ("tubos_valvula", 190.0), ("industrial_fan", 120.0),
    ("background_silo", 420.0), ("tambores", 165.0), ("metal_support", 180.0),
    ("lixo", 125.0), ("industrial_stairs", 200.0), ("sucata", 145.0),
    ("hangar_door_a", 240.0), ("cacamba", 155.0), ("power_pylon", 430.0),
    ("distant_factory", 260.0),
]

# Silhuetas do horizonte (assets/skyline_sprites): fileira de trás e da frente.
SKYLINE_SPRITES = [
    "background_silo", "distant_factory", "power_pylon", "industrial_tower_a",
    "industrial_chimney", "fixed_crane", "pressure_tank", "cargo_elevator",
]
SKYLINE_BACK = [("distant_factory", 70), ("background_silo", 96), ("power_pylon", 110),
                ("industrial_chimney", 84), ("distant_factory", 60), ("industrial_tower_a", 92),
                ("cargo_elevator", 52), ("background_silo", 80), ("power_pylon", 100),
                ("fixed_crane", 88), ("distant_factory", 66), ("pressure_tank", 58)]
SKYLINE_FRONT = [("industrial_tower_a", 128), ("distant_factory", 92), ("industrial_chimney", 140),
                 ("fixed_crane", 120), ("power_pylon", 150), ("pressure_tank", 74),
                 ("background_silo", 132), ("distant_factory", 84), ("cargo_elevator", 70)]

# Cor média da faixa do horizonte do panorama poluído (usada na neblina).
POLLUTED_HAZE: Tuple[int, int, int] = (92, 54, 26)

# Lixo coletável (modelos de sucata de modelos_3d), em ordem fixa de aparição.
TRASH_MODELS = [
    "rusty_can", "chemical_battery", "radio_transceiver", "junkyard_mask",
    "shattered_spotlight", "turbine_debris", "broken_pipe", "scrap_heap",
    "piston_pump", "debris_plate",
]

# Obstáculos (props Dieselpunk). Cada tipo pede uma manobra diferente.
#   low   -> voe POR CIMA      gate  -> passe POR BAIXO      tower -> desvie PARA O LADO
@dataclass(frozen=True)
class ObstacleSpec:
    kind: str
    sprite: str
    visual_height: float   # altura do sprite no mundo
    width: float           # largura da colisão no mundo
    y_min: float           # faixa de altura que colide
    y_max: float

OBSTACLE_SPECS = {
    "low": [
        ObstacleSpec("low", "tambores", 110.0, 150.0, 0.0, 100.0),
        ObstacleSpec("low", "cacamba", 105.0, 165.0, 0.0, 96.0),
        ObstacleSpec("low", "sucata", 85.0, 175.0, 0.0, 80.0),
        ObstacleSpec("low", "lixo", 85.0, 175.0, 0.0, 80.0),
    ],
    "gate": [
        ObstacleSpec("gate", "tubos_valvula", 175.0, 200.0, 105.0, 400.0),
    ],
    "tower": [
        ObstacleSpec("tower", "chamine", 330.0, 80.0, 0.0, 400.0),
        ObstacleSpec("tower", "caldeira", 230.0, 140.0, 0.0, 400.0),
    ],
}
OBSTACLE_KINDS = ("low", "gate", "tower")
POWERUP_KINDS = ("shield", "magnet", "repair")

# Aviões de papel do "Estúdio 3D Aviões, 14-Bis & Piloto" e opções de piloto.
PLANE_MODELS: List[Tuple[str, str]] = [
    ("dart", "1. Jato Alongado (Com Clipe)"),
    ("glider", "2. Planador Largo"),
    ("stubby", "3. Asa Curta e Ponta Larga"),
    ("binder", "4. Avião de Fichário"),
    ("needle", "5. Bico Agulha"),
    ("hoverboard", "6. Hoverboard (Asa Retangular)"),
    ("crane", "7. Tsuru / Pássaro"),
    ("accordion", "8. Sanfona"),
    ("jetfighter", "9. Caça Realista"),
    ("tailboom", "10. Planador de Haste Longa"),
    ("bis14", "11. 14-Bis (Miniatura de Papelão)"),
]
PILOTS: List[Tuple[str, str]] = [
    ("none", "Sem piloto"),
    ("riding", "Boneco montado"),
    ("surfing", "Boneco surfando"),
    ("zen", "Boneco zen"),
    ("waving", "Boneco acenando"),
    ("superman", "Boneco super-herói"),
    ("wheelchair", "Boneco na cadeira de rodas"),
]

# Oficina de pintura: cores aplicadas ao papel do avião (o piloto não muda).
# "original" usa as cores do estúdio (sem tinta). Cada avião lembra a sua cor.
PLANE_COLORS: List[Tuple[str, str, Optional[Tuple[int, int, int]]]] = [
    ("original", "Original do estúdio", None),
    ("branco", "Branco papel", (250, 250, 246)),
    ("vermelho", "Vermelho", (229, 57, 53)),
    ("laranja", "Laranja", (251, 140, 0)),
    ("amarelo", "Amarelo", (253, 216, 53)),
    ("verde", "Verde", (67, 160, 71)),
    ("menta", "Verde-água", (38, 198, 160)),
    ("ciano", "Ciano", (0, 188, 212)),
    ("azul", "Azul", (30, 136, 229)),
    ("anil", "Anil", (63, 81, 181)),
    ("roxo", "Roxo", (142, 36, 170)),
    ("rosa", "Rosa", (236, 64, 122)),
    ("dourado", "Dourado", (212, 175, 55)),
    ("kraft", "Papelão kraft", (196, 160, 110)),
    ("grafite", "Grafite", (84, 90, 100)),
]
PLANE_COLOR_KEYS = [key for key, _, _ in PLANE_COLORS]

# Padrões de pintura do estúdio 3D (segunda linha da Oficina). Cada padrão é uma
# textura 256×256 em assets/plane_patterns, desenhada pelo próprio estúdio com as
# cores dos presets dele; o jogo a "veste" no papel do avião usando o mapa UV de
# cada combinação (assets/plane_uv e plane_menu_uv). "liso" usa só a cor escolhida.
PLANE_PATTERNS: List[Tuple[str, str]] = [
    ("liso", "Liso (só a cor)"), ("camuflado", "Camuflado selva"), ("deserto", "Camuflado deserto"),
    ("artico", "Camuflado ártico"), ("chamas", "Chamas hot rod"), ("plasma", "Chamas de plasma"),
    ("galaxia", "Galáxia estelar"), ("cyberpunk", "Cyberpunk neon"), ("tigre", "Tigre selvagem"),
    ("hexagonal", "Fibra hexagonal"), ("prisma", "Prisma (dazzle)"), ("xadrez", "Xadrez de corrida"),
    ("listras", "Listras de corrida"), ("raios", "Raios solares"), ("pop_art", "Pop art (retícula)"),
    ("brasil", "Brasil"),
]
PLANE_PATTERN_KEYS = [key for key, _ in PLANE_PATTERNS]
PATTERN_TEXTURE_SIZE = 256
PATTERN_CACHE_LIMIT = 4        # paletas de padrão prontas na memória (~2,7 MB cada)


# Manobras: curvas extraídas das animações glTF do pacote 3D (tools/extract_maneuvers.py
# grava assets/maneuvers/maneuvers.json). São só visuais: a colisão usa a posição real.
@dataclass(frozen=True)
class ManeuverStyle:
    label: str
    duration: float    # segundos no jogo
    sway: float        # deslocamento lateral máximo (em larguras do avião)
    lift: float        # deslocamento vertical máximo (em larguras do avião)
    depth: float       # quanto o avião encolhe ao se afastar (dz = 1)


MANEUVER_STYLES = {
    "tonneau": ManeuverStyle("Tonneau (giro de 360°)", 0.95, 0.35, 0.3, 0.2),
    "looping": ManeuverStyle("Looping vertical", 1.5, 0.3, 0.55, 0.3),
    "cobra": ManeuverStyle("Manobra cobra", 1.2, 0.3, 0.4, 0.25),
    "decolagem": ManeuverStyle("Decolagem", 1.4, 0.4, 0.5, 0.3),
}
POWERUP_MANEUVERS = {"shield": "looping", "magnet": "tonneau", "repair": "cobra"}
START_MANEUVER = "decolagem"
MANEUVER_MIN_THICKNESS = 0.28  # de perfil (nariz para cima) o sprite não some
MANEUVER_TOP_MARGIN = 70       # px: o centro do avião não sobe além disto durante a manobra


def builtin_maneuvers() -> dict:
    """Curvas de reserva (mesmo formato do JSON), usadas se o arquivo faltar."""
    curves = {}
    n = 33
    for name in MANEUVER_STYLES:
        rows = []
        for i in range(n):
            t = i / (n - 1)
            s = math.sin(math.pi * t)
            if name == "tonneau":
                rows.append((t, -360.0 * t, 0.0, 0.2 * math.sin(2 * math.pi * t), s, 0.4 * s))
            elif name == "looping":
                rows.append((t, 0.0, 360.0 * t, 0.0, (1 - math.cos(2 * math.pi * t)) / 2,
                             0.5 * math.sin(2 * math.pi * t)))
            elif name == "cobra":
                rows.append((t, 0.0, 78.0 * s * s, 0.0, 0.25 * s, s))
            else:
                rows.append((t, 0.0, 20.0 * (1 - t), 0.0, -0.25 * (1 - t), -(1 - t)))
        curves[name] = rows
    return curves


def load_maneuvers() -> dict:
    """Lê assets/maneuvers/maneuvers.json: por manobra, linhas (t, roll, pitch, dx, dy, dz)."""
    curves = builtin_maneuvers()
    for folder in asset_dir_candidates("maneuvers"):
        path = folder / "maneuvers.json"
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for name in MANEUVER_STYLES:
                rows = data.get(name, {}).get("samples")
                if rows and len(rows) >= 2 and all(len(r) == 6 for r in rows):
                    curves[name] = [tuple(float(v) for v in r) for r in rows]
            break
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return curves


@dataclass
class Entity:
    z: float
    lane: int
    kind: str                 # trash | low | gate | tower | shield | magnet | repair
    y: float = 0.0            # altura (lixo e power-ups flutuam)
    sprite: str = ""          # modelo usado no desenho
    collected: bool = False

    @property
    def x(self) -> float:
        return self.lane * LANE_WIDTH

@dataclass
class Beam:
    x: float
    z: float
    ttl: float = 0.18

@dataclass
class FloatingText:
    text: str
    x: float
    y: float
    ttl: float = 0.9

@dataclass(frozen=True)
class Hitbox:
    """Caixa de colisão no mundo 3D (x lateral, y altura, z profundidade)."""
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    z_min: float
    z_max: float

    def intersects(self, other: "Hitbox") -> bool:
        return (
            self.x_min <= other.x_max and self.x_max >= other.x_min
            and self.y_min <= other.y_max and self.y_max >= other.y_min
            and self.z_min <= other.z_max and self.z_max >= other.z_min
        )


def obstacle_spec(entity: Entity) -> ObstacleSpec:
    for spec in OBSTACLE_SPECS.get(entity.kind, []):
        if spec.sprite == entity.sprite:
            return spec
    return OBSTACLE_SPECS[entity.kind][0]


class Game:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Eco Runner — Aviões de Papel: Dieselpunk to Solarpunk")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("segoeui", 18)
        self.small_font = pygame.font.SysFont("segoeui", 14)
        self.title_font = pygame.font.SysFont("segoeui", 32, bold=True)
        self.side_prop_sprites = self.load_dieselpunk_sprites()
        self.tree_sprites = self.load_sprite_set("solarpunk_sprites", [n for n, _ in SOLARPUNK_TREE_SPECS])
        self.trash_sprites = self.load_sprite_set("trash_sprites", TRASH_MODELS)
        self.powerup_sprites = self.load_powerup_sprites()
        combos = [f"{m}__{p}" for m, _ in PLANE_MODELS for p, _ in PILOTS]
        self.plane_sprites = self.load_sprite_set("plane_sprites", combos)
        self.plane_menu_sprites = self.load_sprite_set("plane_menu", combos)
        self.plane_paint = self.load_sprite_set("plane_paint", combos)
        self.plane_menu_paint = self.load_sprite_set("plane_menu_paint", combos)
        self.plane_uv = self.load_sprite_set("plane_uv", combos)
        self.plane_menu_uv = self.load_sprite_set("plane_menu_uv", combos)
        self.pattern_textures = self.load_pattern_textures()
        self.pattern_palettes: dict = {}
        self.uv_indices: dict = {}
        self.pattern_thumbs: dict = {}
        self.painted_cache: dict = {}
        self.maneuver_curves = load_maneuvers()
        self.scenario_sprites = self.load_sprite_set("scenario_sprites", SCENARIO_SPRITES)
        self.skyline_sprites = self.load_sprite_set("skyline_sprites", SKYLINE_SPRITES)
        atmosphere = self.load_sprite_set("atmosphere", ["sky_panorama", "smog_cloud"])
        self.sprite_cache: dict = {}
        self.flipped_sprite_cache: dict = {}
        self.mip_cache: dict = {}
        self.sky_cache: dict = {}
        self.skyline_cache: dict = {}
        self.skyline_state: dict = {}
        self.shadow_cache: dict = {}
        self.warm_up_queue = self.warm_up_tasks()
        ground = self.load_sprite_set("ground", ["grass", "concrete"])
        self.ground_textures = {name: surface.convert() for name, surface in ground.items()}
        self.grass_texture = self.ground_textures.get("grass")
        self.concrete_texture = self.ground_textures.get("concrete")
        self.ground_groups: dict = {}
        self.ground_fog_cache: dict = {}
        self.ground_rows = self.compute_ground_rows()
        self.sky_panorama = self.prepare_panorama(atmosphere.get("sky_panorama"))
        self.clouds = self.prepare_clouds(atmosphere.get("smog_cloud"))
        self.pollution = 1.0
        self.fog_color: Color = POLLUTED_HAZE
        self.fog_sprite_color: Color = POLLUTED_HAZE
        self.smooth_dt = 1.0 / FPS
        self.running = True
        self.high_score = self.load_high_score()
        self.plane_index, self.pilot_index = self.load_selection()
        self.plane_colors = self.load_plane_colors()
        self.plane_patterns = self.load_plane_patterns()
        self.control_mode = self.load_control_mode()
        self.webcam: Optional[WebcamControl] = None     # criado ao usar a câmera
        self.analog = (0.0, 0.0)                        # eixos da câmera: (direita, subir), -1..1
        self.webcam_surface: Optional[pygame.Surface] = None
        self.webcam_surface_bytes: Optional[bytes] = None
        self.cheat_keys: List[int] = []                 # últimas teclas do hangar
        self.cheat_armed = False                        # vale para a próxima partida
        self.cheat_invincible = False                   # ativo na partida atual
        self.cheat_flash = 0.0
        if self.uses_camera:
            self.ensure_webcam()                        # calibra enquanto você está no hangar
        self.paint_index = 0
        self.pattern_index = 0
        self.paint_row = 0           # 0 = cor, 1 = padrão (linha ativa na Oficina)
        self.paint_before = "original"
        self.pattern_before = "liso"
        self.state = "menu"          # menu (hangar) | playing
        self.reset()

    # ------------------------------------------------------------------ assets
    @staticmethod
    def load_sprite_set(folder: str, names: List[str]) -> dict:
        """Carrega PNGs opcionais; arquivos ausentes ou inválidos usam fallback.

        Cada sprite é procurado em todas as pastas candidatas, então um PNG
        adicionado ao lado do executável substitui o embutido.
        """
        sprites = {}
        dirs = [d for d in asset_dir_candidates(folder) if d.is_dir()]
        for name in names:
            for sprite_dir in dirs:
                path = sprite_dir / f"{name}.png"
                if not path.is_file():
                    continue
                try:
                    sprites[name] = pygame.image.load(str(path)).convert_alpha()
                    break
                except (OSError, pygame.error):
                    continue
        return sprites

    def load_pattern_textures(self) -> dict:
        """Texturas dos padrões de pintura, sempre em 256×256 (o mapa UV usa 8 bits)."""
        textures = {}
        loaded = self.load_sprite_set("plane_patterns", PLANE_PATTERN_KEYS[1:])
        size = (PATTERN_TEXTURE_SIZE, PATTERN_TEXTURE_SIZE)
        for key, surface in loaded.items():
            if surface.get_size() != size:
                surface = pygame.transform.smoothscale(surface, size)
            textures[key] = surface
        return textures

    def load_dieselpunk_sprites(self) -> dict:
        return self.load_sprite_set("dieselpunk_sprites", [name for name, _ in DIESELPUNK_PROP_SPECS])

    def load_powerup_sprites(self) -> dict:
        return self.load_sprite_set("powerup_sprites", list(POWERUP_KINDS))

    def cache_put(self, cache: dict, key: tuple, value: pygame.Surface) -> None:
        """Guarda no cache descartando os itens mais antigos aos poucos.

        Antes o cache era esvaziado de uma vez ao lotar, o que obrigava a
        reescalar dezenas de sprites no mesmo quadro (engasgo visível).
        """
        while len(cache) >= SPRITE_CACHE_LIMIT:
            cache.pop(next(iter(cache)))
        cache[key] = value

    def mip_levels(self, sprite: pygame.Surface, key: tuple, flip: bool) -> List[pygame.Surface]:
        """Versões pré-reduzidas do sprite (1, 1/2, 1/4...), já espelhadas se preciso.

        Reduzir a partir do nível mais próximo é muito mais barato do que
        reduzir o PNG de 368 px inteiro a cada novo tamanho.
        """
        levels = self.mip_cache.get((key, flip))
        if levels is None:
            base = pygame.transform.flip(sprite, True, False) if flip else sprite
            levels = [base]
            while min(levels[-1].get_size()) > 20:
                w, h = levels[-1].get_size()
                levels.append(pygame.transform.smoothscale(levels[-1], (max(1, int(w / 1.5)), max(1, int(h / 1.5)))))
            self.mip_cache[(key, flip)] = levels
        return levels

    def scaled_sprite(self, sprite: pygame.Surface, key: tuple, size: Tuple[int, int], flip: bool = False) -> pygame.Surface:
        cache_key = (key, size, flip)
        scaled = self.sprite_cache.get(cache_key)
        if scaled is None:
            source = None
            for level in reversed(self.mip_levels(sprite, key, flip)):
                if level.get_width() >= size[0] and level.get_height() >= size[1]:
                    source = level
                    break
            if source is None:
                source = self.mip_levels(sprite, key, flip)[0]
            if source.get_size() == size:
                scaled = source
            elif size[1] < 40:
                # Pequenos e distantes: o nível de redução já está perto do tamanho final.
                scaled = pygame.transform.scale(source, size)
            else:
                scaled = pygame.transform.smoothscale(source, size)
            self.cache_put(self.sprite_cache, cache_key, scaled)
        return scaled

    def fogged_sprite(self, scaled: pygame.Surface, cache_key: tuple, level: int) -> pygame.Surface:
        """Mistura o sprite à cor da neblina (nível 1..FOG_LEVELS-1)."""
        key = ("fog", cache_key, level, self.fog_sprite_color)
        tinted = self.sprite_cache.get(key)
        if tinted is None:
            amount = level / FOG_LEVELS
            mix = min(0.9, amount * 0.95)
            keep = int(255 * (1.0 - mix))
            tinted = scaled.copy()
            alpha = 255 if amount < 0.75 else int(255 * clamp((1.0 - amount) / 0.25, 0.0, 1.0))
            tinted.fill((keep, keep, keep, alpha), special_flags=pygame.BLEND_RGBA_MULT)
            r, g, b = self.fog_sprite_color
            tinted.fill((int(r * mix), int(g * mix), int(b * mix), 0), special_flags=pygame.BLEND_RGBA_ADD)
            self.cache_put(self.sprite_cache, key, tinted)
        return tinted

    def fog_level(self, z: float) -> int:
        amount = clamp((z - FOG_START) / (FOG_END - FOG_START), 0.0, 1.0)
        return int(amount * FOG_LEVELS + 0.5)

    # ------------------------------------------------------------ atmosfera
    @staticmethod
    def prepare_panorama(panorama: Optional[pygame.Surface]) -> Optional[pygame.Surface]:
        """Recorta o céu do panorama do kit até a linha do horizonte e ajusta à tela."""
        if panorama is None:
            return None
        w, h = panorama.get_size()
        horizon_row = int(h * 0.725)               # faixa alaranjada do horizonte no panorama
        scaled_w = int(w * SKY_PANORAMA_SCALE)
        scaled_h = int(h * SKY_PANORAMA_SCALE)
        big = pygame.transform.smoothscale(panorama, (scaled_w, scaled_h))
        top = max(0, int(horizon_row * SKY_PANORAMA_SCALE) - HORIZON_Y)
        sky = pygame.Surface((scaled_w, HORIZON_Y))
        sky.blit(big, (0, -top))
        return sky.convert()

    @staticmethod
    def prepare_clouds(smog: Optional[pygame.Surface]) -> List[dict]:
        """Nuvens em posições fixas: versão de fumaça (eras poluídas) e versão limpa."""
        if smog is None:
            return []
        layout = [  # x, y, largura, deriva, paralaxe, opacidade
            (60, 18, 420, 0.010, 0.55, 0.95), (520, 70, 300, 0.016, 0.80, 0.85),
            (900, 30, 460, 0.008, 0.45, 0.95), (1300, 110, 260, 0.020, 1.00, 0.75),
            (1620, 52, 380, 0.012, 0.65, 0.90), (260, 128, 220, 0.024, 1.15, 0.70),
            (1120, 150, 240, 0.022, 1.10, 0.65),
        ]
        clouds = []
        for x, y, w, drift, parallax, opacity in layout:
            h = int(w * 0.42)
            smoke = pygame.transform.smoothscale(smog, (w, h))
            # Clareia um pouco a fumaça para ela aparecer sobre o céu escuro.
            smoke.fill((38, 30, 24, 0), special_flags=pygame.BLEND_RGBA_ADD)
            clean = smoke.copy()
            clean.fill((255, 255, 255, 0), special_flags=pygame.BLEND_RGB_MAX)
            clouds.append({"x": float(x), "y": y, "w": w, "drift": drift, "parallax": parallax,
                           "opacity": opacity, "smoke": smoke, "clean": clean, "baked": {}})
        return clouds

    def update_atmosphere(self, horizon: Color) -> None:
        """Poluição do céu e cor da neblina conforme a restauração."""
        self.pollution = clamp(1.0 - (self.restoration - POLLUTION_CLEAR_START)
                               / (POLLUTION_CLEAR_END - POLLUTION_CLEAR_START), 0.0, 1.0)
        fog = lerp_color(horizon, POLLUTED_HAZE, self.pollution * 0.8)
        self.fog_color = tuple(int(c) for c in fog)  # type: ignore[assignment]
        # Versão arredondada para os sprites: só refaz a neblina deles quando a
        # cor muda de faixa (antes refazia a cada coleta de lixo).
        self.fog_sprite_color = tuple(int(c) // 12 * 12 + 6 for c in fog)  # type: ignore[assignment]

    def sky_gradient(self, top: Color, horizon: Color) -> pygame.Surface:
        key = (tuple(c // 4 for c in top), tuple(c // 4 for c in horizon))
        surface = self.sky_cache.get(key)
        if surface is None:
            if len(self.sky_cache) > 24:
                self.sky_cache.clear()
            column = pygame.Surface((1, HORIZON_Y))
            for y in range(HORIZON_Y):
                column.set_at((0, y), lerp_color(top, horizon, y / max(1, HORIZON_Y - 1)))
            surface = pygame.transform.scale(column, (WIDTH, HORIZON_Y)).convert()
            self.sky_cache[key] = surface
        return surface

    def blit_tiled(self, surface: pygame.Surface, offset: float, y: int) -> None:
        """Desenha uma faixa que se repete na horizontal, deslocada por offset."""
        tile = surface.get_width()
        x = -(offset % tile)
        while x < WIDTH:
            self.screen.blit(surface, (int(x), y))
            x += tile

    def draw_sky_panorama(self) -> None:
        if self.sky_panorama is None or self.pollution <= 0.01:
            return
        self.sky_panorama.set_alpha(int(235 * self.pollution))
        offset = self.cam_x * SKY_SHIFT_PX + self.distance_travelled * SKY_DRIFT_PX + 260
        self.blit_tiled(self.sky_panorama, offset, 0)

    def draw_clouds(self) -> None:
        for cloud in self.clouds:
            shift = (self.distance_travelled * cloud["drift"]
                     + self.cam_x * CLOUD_SHIFT_PX * cloud["parallax"])
            x = (cloud["x"] - shift) % CLOUD_TILE - cloud["w"]
            if x > WIDTH:
                continue
            for variant, strength in (("smoke", 0.85 * self.pollution), ("clean", 0.6 * (1.0 - self.pollution))):
                surface = self.cloud_surface(cloud, variant, strength * cloud["opacity"])
                if surface is not None:
                    self.screen.blit(surface, (int(x), cloud["y"]))

    @staticmethod
    def cloud_surface(cloud: dict, variant: str, strength: float) -> Optional[pygame.Surface]:
        """Nuvem com a transparência já aplicada nos pixels (blit rápido).

        A opacidade é arredondada em 12 níveis e cada nível é preparado uma vez.
        """
        level = int(clamp(strength, 0.0, 1.0) * 12 + 0.5)
        if level <= 0:
            return None
        key = (variant, level)
        surface = cloud["baked"].get(key)
        if surface is None:
            surface = cloud[variant].copy()
            if level < 12:
                surface.fill((255, 255, 255, int(255 * level / 12)), special_flags=pygame.BLEND_RGBA_MULT)
            cloud["baked"][key] = surface
        return surface

    def build_skyline(self, layout: List[Tuple[str, int]], sprites: dict) -> Optional[pygame.Surface]:
        """Monta uma faixa contínua de silhuetas (repete a cada FAR_TILE px)."""
        items = [(sprites[name], h) for name, h in layout if name in sprites]
        if not items:
            return None
        strip = pygame.Surface((FAR_TILE, SKYLINE_HEIGHT), pygame.SRCALPHA)
        x = 0.0
        i = 0
        while x < FAR_TILE:
            sprite, h = items[i % len(items)]
            w = max(2, int(sprite.get_width() * h / sprite.get_height()))
            scaled = pygame.transform.smoothscale(sprite, (w, h))
            for dx in (0, -FAR_TILE):              # repete o que passa da borda: emenda invisível
                strip.blit(scaled, (int(x) + dx, SKYLINE_HEIGHT - h))
            x += w * 0.78 + 14 + (i * 37) % 45
            i += 1
        return strip

    def skyline_base(self, name: str) -> Optional[pygame.Surface]:
        """Faixa de silhuetas sem neblina (montada uma vez)."""
        key = (name, "base")
        if key not in self.skyline_cache:
            if name == "trees":
                layout = [(n, int(h * 0.42)) for n, h in SOLARPUNK_TREE_SPECS]
                self.skyline_cache[key] = self.build_skyline(layout, self.tree_sprites)
            else:
                layout = SKYLINE_BACK if name == "back" else SKYLINE_FRONT
                self.skyline_cache[key] = self.build_skyline(layout, self.skyline_sprites)
        return self.skyline_cache[key]

    def skyline_target(self) -> Tuple[int, tuple]:
        """Estado desejado das silhuetas: troca indústria → árvores e cor da neblina."""
        industrial = clamp(self.pollution * 1.4, 0.0, 1.0) if self.tree_sprites else 1.0
        return int(industrial * 10 + 0.5), tuple(c // 16 for c in self.fog_color)

    def skyline_job(self, name: str, target: Tuple[int, tuple]) -> dict:
        """Prepara uma fileira nova em pedaços de SKYLINE_CHUNK px.

        Refazer a faixa inteira de uma vez custava ~7 ms e causava engasgos;
        em pedaços, o trabalho se espalha por alguns quadros e a faixa antiga
        continua na tela até a nova ficar pronta.
        """
        level = target[0]
        parts = []
        industrial = self.skyline_base(name)
        if industrial is not None and level > 0:
            parts.append((industrial, SKYLINE_HAZE[name], level / 10))
        trees = self.skyline_base("trees") if name == "front" else None
        if trees is not None and level < 10:
            parts.append((trees, SKYLINE_HAZE["trees"], 1.0 - level / 10))
        surface = pygame.Surface((FAR_TILE, SKYLINE_HEIGHT), pygame.SRCALPHA) if parts else None
        fog = self.fog_color

        def steps():
            for x in range(0, FAR_TILE, SKYLINE_CHUNK):
                rect = pygame.Rect(x, 0, min(SKYLINE_CHUNK, FAR_TILE - x), SKYLINE_HEIGHT)
                dest = surface.subsurface(rect)
                for i, (base, haze, alpha) in enumerate(parts):
                    piece = dest if i == 0 else pygame.Surface(rect.size, pygame.SRCALPHA)
                    piece.blit(base.subsurface(rect), (0, 0), special_flags=pygame.BLEND_RGBA_MAX)
                    keep = int(255 * (1.0 - haze))
                    piece.fill((keep, keep, keep, int(255 * alpha)), special_flags=pygame.BLEND_RGBA_MULT)
                    piece.fill((int(fog[0] * haze), int(fog[1] * haze), int(fog[2] * haze), 0),
                               special_flags=pygame.BLEND_RGBA_ADD)
                    if piece is not dest:
                        dest.blit(piece, (0, 0))
                yield

        return {"target": target, "surface": surface, "steps": steps() if parts else iter(())}

    def update_skyline(self, budget_ms: float) -> None:
        target = self.skyline_target()
        start = time.perf_counter()
        for name in ("back", "front"):
            state = self.skyline_state.setdefault(name, {"surface": None, "target": None, "job": None})
            if state["job"] is None and state["target"] != target:
                state["job"] = self.skyline_job(name, target)
            job = state["job"]
            if job is None:
                continue
            first_time = state["target"] is None      # primeira vez: monta tudo já
            while first_time or (time.perf_counter() - start) * 1000.0 < budget_ms:
                if next(job["steps"], StopIteration) is StopIteration:
                    state["surface"], state["target"], state["job"] = job["surface"], job["target"], None
                    break

    def draw_skyline(self, horizon: Color) -> None:
        """Camada distante: duas fileiras de silhuetas dos modelos, bem lentas."""
        self.update_skyline(SKYLINE_BUDGET_MS)
        drift = self.distance_travelled * FAR_DRIFT_PX
        shift = self.cam_x * FAR_SHIFT_PX
        drew = False
        for name, ratio, extra in (("back", FAR_BACK_RATIO, 700), ("front", 1.0, 0)):
            layer = self.skyline_state.get(name, {}).get("surface")
            if layer is None:
                continue
            drew = True
            self.blit_tiled(layer, (shift + drift) * ratio + extra, HORIZON_Y - SKYLINE_HEIGHT + 2)
        if not drew and self.skyline_base("back") is None and self.skyline_base("front") is None:
            self.draw_far_layer(horizon)

    # ---------------------------------------------------------------- chão
    @staticmethod
    def compute_ground_rows() -> List[Tuple[int, float, int]]:
        """Para cada linha da tela entre o fim da neblina e a base: (y, profundidade, grupo de escala).

        A câmera tem altura fixa, então cada linha da tela corresponde sempre à
        mesma profundidade do chão; só a textura desliza sobre ela. Acima de
        FOG_END o chão já está todo na cor da neblina e não precisa de textura.
        """
        rows = []
        for y in range(HORIZON_Y + 1, HEIGHT):
            z = CAMERA_HEIGHT * FOV / (y + 0.5 - HORIZON_Y)
            if z > FOG_END:
                continue
            scale = FOV / z
            rows.append((y, z, int(round(math.log(scale) / math.log(GROUND_ROW_GROUP)))))
        return rows

    def ground_group(self, name: str, group: int) -> Tuple[pygame.Surface, int]:
        """Textura do chão reduzida na escala do grupo e repetida na largura da tela."""
        cached = self.ground_groups.get((name, group))
        if cached is None:
            texture = self.ground_textures[name]
            tile_x = GROUND_TILES[name][0]
            tile_w = max(4, int(round(tile_x * GROUND_ROW_GROUP ** group)))
            tex_h = texture.get_height()
            tile = pygame.transform.smoothscale(texture, (tile_w, tex_h))
            # Faixa com ~GROUND_STRIP_MIN px (várias repetições): cada linha da tela
            # é montada com 2 a 4 pedaços dela, sem guardar a largura toda da tela.
            copies = max(1, math.ceil(GROUND_STRIP_MIN / tile_w))
            strip = pygame.Surface((tile_w * copies, tex_h)).convert()
            for x in range(0, strip.get_width(), tile_w):
                strip.blit(tile, (x, 0))
            cached = (strip, tile_w)
            self.ground_groups[(name, group)] = cached
        return cached

    def ground_row_info(self, name: str, group: int) -> Optional[tuple]:
        """Dados prontos de uma faixa (evita recalcular a cada linha e quadro)."""
        key = ("info", name, group)
        info = self.ground_groups.get(key, False)
        if info is False:
            texture = self.ground_textures.get(name)
            if texture is None:
                info = None
            else:
                strip, tile_w = self.ground_group(name, group)
                tile_x, tile_z = GROUND_TILES[name]
                info = (strip, tile_w, strip.get_width(), tile_x, tile_z, texture.get_height())
            self.ground_groups[key] = info
        return info

    def ground_fog_overlay(self) -> Tuple[pygame.Surface, int]:
        """Faixa transparente na cor da neblina para o chão distante (refeita se a cor mudar)."""
        y_far = int(HORIZON_Y + CAMERA_HEIGHT * FOV / FOG_END)
        y_near = int(HORIZON_Y + CAMERA_HEIGHT * FOV / FOG_START) + 1
        key = self.fog_color
        overlay = self.ground_fog_cache.get(key)
        if overlay is None:
            self.ground_fog_cache.clear()
            column = pygame.Surface((1, y_near - y_far), pygame.SRCALPHA)
            for i in range(y_near - y_far):
                z = CAMERA_HEIGHT * FOV / (y_far + i + 0.5 - HORIZON_Y)
                haze = clamp((z - FOG_START) / (FOG_END - FOG_START), 0.0, 1.0)
                column.set_at((0, i), (*self.fog_color, int(255 * haze)))
            overlay = pygame.transform.scale(column, (WIDTH, y_near - y_far))
            self.ground_fog_cache[key] = overlay
        return overlay, y_far

    def grass_start_row(self, wave_z: float) -> int:
        """Linha da tela onde a grama começa (HEIGHT = sem grama)."""
        if self.restoration < GRASS_START_RESTORATION:
            return HEIGHT
        return int(HORIZON_Y + CAMERA_HEIGHT * FOV / wave_z)

    def draw_ground(self, wave_z: float) -> None:
        """Chão fora da pista: concreto sujo onde não foi restaurado, grama onde já foi.

        Desenhado linha a linha da tela: cada linha copia a linha certa da
        textura, na escala da sua profundidade, deslocada pela distância
        percorrida (o chão vem na direção do avião) e pela câmera (paralaxe
        igual à da pista). A grama começa na frente de restauração, onde as
        árvores aparecem; antes dela (e em toda a fase inicial) é concreto.
        """
        if not self.ground_textures:
            return
        y_grass = self.grass_start_row(wave_z)
        distance = self.distance_travelled
        cam = self.cam_x
        jobs = []
        append = jobs.append
        for y, z, group in self.ground_rows:
            name = "grass" if y >= y_grass else "concrete"
            info = self.ground_row_info(name, group)
            if info is None:
                continue
            strip, tile_w, strip_w, tile_x, tile_z, tex_h = info
            # Só as laterais: a pista (desenhada depois) cobre o meio da linha,
            # e perto da câmera cobre a linha inteira.
            scale = FOV / z
            road_left = int(WIDTH / 2 + (-ROAD_WIDTH / 2 - cam) * scale) + 2
            road_right = int(WIDTH / 2 + (ROAD_WIDTH / 2 - cam) * scale) - 2
            if road_left <= 0 and road_right >= WIDTH:
                continue
            origin = ((cam - (WIDTH / 2) * tile_x / tile_w) / tile_x) % 1.0 * tile_w
            v = int((z + distance) / tile_z % 1.0 * tex_h)
            for start, stop in ((0, min(road_left, WIDTH)), (max(road_right, 0), WIDTH)):
                x = start
                src = int(origin + start) % tile_w
                while x < stop:
                    piece = min(strip_w - src, stop - x)
                    append((strip, (x, y), (src, v, piece, 1)))
                    x += piece
                    src = 0
        self.screen.blits(jobs, doreturn=False)
        if self.concrete_texture is not None and y_grass > HORIZON_Y:
            near_z = wave_z if y_grass < HEIGHT else CAMERA_HEIGHT * FOV / (HEIGHT - HORIZON_Y)
            self.draw_concrete_joints(near_z)
        overlay, y_far = self.ground_fog_overlay()
        self.screen.blit(overlay, (0, y_far))
        if y_grass < HEIGHT:
            # Borda da grama: linha escura que marca onde a restauração chegou.
            haze = clamp((wave_z - FOG_START) / (FOG_END - FOG_START), 0.0, 1.0)
            pygame.draw.line(self.screen, lerp_color((38, 84, 32), self.fog_color, haze),
                             (0, y_grass), (WIDTH, y_grass), 2)

    def draw_concrete_joints(self, near_z: float) -> None:
        """Juntas das placas paralelas à pista, em perspectiva exata (linhas retas no chão)."""
        if near_z >= FOG_START:
            pieces = [near_z, FOG_END]
        else:
            pieces = [near_z] + [FOG_START + (FOG_END - FOG_START) * k / 4 for k in range(5)]
        for x in CONCRETE_JOINTS_X:
            for side in (-1, 1):
                for z0, z1 in zip(pieces, pieces[1:]):
                    if z1 <= z0:
                        continue
                    haze = clamp((z0 - FOG_START) / (FOG_END - FOG_START), 0.0, 1.0)
                    p0 = self.project(side * x, 0, z0)
                    p1 = self.project(side * x, 0, z1)
                    pygame.draw.line(self.screen, lerp_color(CONCRETE_JOINT_COLOR, self.fog_color, haze),
                                     (p0[0], p0[1]), (p1[0], p1[1]), max(1, int(2.2 * p0[2])))

    def warm_up_tasks(self):
        """Tarefas de preparo (reduções dos sprites e silhuetas), uma por vez."""
        for name in ("back", "front", "trees"):
            yield lambda name=name: self.skyline_base(name)
        for name in self.ground_textures:
            for group in sorted({g for _, _, g in self.ground_rows}):
                yield lambda name=name, group=group: self.ground_group(name, group)
        groups = (
            ("scenery", self.scenario_sprites), ("scenery", self.side_prop_sprites),
            ("tree", self.tree_sprites), ("trash", self.trash_sprites),
            ("powerup", self.powerup_sprites),
        )
        for prefix, sprites in groups:
            for name, sprite in sprites.items():
                for flip in ((False, True) if prefix in ("scenery", "tree") else (False,)):
                    yield lambda s=sprite, k=(prefix, name), f=flip: self.mip_levels(s, k, f)

    def step_warm_up(self, budget_ms: float) -> None:
        """Prepara sprites aos poucos (no hangar), para a partida não engasgar."""
        if self.warm_up_queue is None:
            return
        start = time.perf_counter()
        while (time.perf_counter() - start) * 1000.0 < budget_ms:
            task = next(self.warm_up_queue, None)
            if task is None:
                self.warm_up_queue = None
                return
            task()

    # --------------------------------------------------------------- seleção
    @property
    def plane_key(self) -> str:
        return PLANE_MODELS[self.plane_index][0]

    @property
    def pilot_key(self) -> str:
        return PILOTS[self.pilot_index][0]

    @property
    def plane_combo(self) -> str:
        return f"{self.plane_key}__{self.pilot_key}"

    @property
    def plane_color_key(self) -> str:
        key = self.plane_colors.get(self.plane_key, "original")
        return key if key in PLANE_COLOR_KEYS else "original"

    @property
    def plane_color(self) -> Optional[Tuple[int, int, int]]:
        return PLANE_COLORS[PLANE_COLOR_KEYS.index(self.plane_color_key)][2]

    @property
    def plane_pattern_key(self) -> str:
        key = self.plane_patterns.get(self.plane_key, "liso")
        return key if key in PLANE_PATTERN_KEYS else "liso"

    @property
    def plane_look(self) -> str:
        """Identifica o visual atual (modelo, piloto, cor e padrão) para os caches de desenho."""
        return f"{self.plane_combo}@{self.plane_color_key}+{self.plane_pattern_key}"

    def paint_label(self) -> str:
        """Descrição curta da pintura atual (hangar)."""
        if self.plane_pattern_key != "liso":
            return f"padrão: {PLANE_PATTERNS[PLANE_PATTERN_KEYS.index(self.plane_pattern_key)][1]}"
        return f"cor: {PLANE_COLORS[PLANE_COLOR_KEYS.index(self.plane_color_key)][1]}"

    @staticmethod
    def load_control_mode() -> str:
        try:
            data = json.loads((user_data_dir() / CONFIG_FILENAME).read_text(encoding="utf-8"))
            mode = data.get("controle", "teclado")
        except (OSError, ValueError, TypeError, AttributeError):
            return "teclado"
        return mode if mode in CONTROL_MODES else "teclado"

    @staticmethod
    def load_plane_patterns() -> dict:
        try:
            data = json.loads((user_data_dir() / CONFIG_FILENAME).read_text(encoding="utf-8"))
            patterns = data.get("padroes", {})
            models = {k for k, _ in PLANE_MODELS}
            return {m: c for m, c in patterns.items() if m in models and c in PLANE_PATTERN_KEYS}
        except (OSError, ValueError, TypeError, AttributeError):
            return {}

    @staticmethod
    def load_plane_colors() -> dict:
        try:
            data = json.loads((user_data_dir() / CONFIG_FILENAME).read_text(encoding="utf-8"))
            colors = data.get("cores", {})
            models = {k for k, _ in PLANE_MODELS}
            return {m: c for m, c in colors.items() if m in models and c in PLANE_COLOR_KEYS}
        except (OSError, ValueError, TypeError, AttributeError):
            return {}

    @staticmethod
    def load_selection() -> Tuple[int, int]:
        try:
            data = json.loads((user_data_dir() / CONFIG_FILENAME).read_text(encoding="utf-8"))
            planes = [k for k, _ in PLANE_MODELS]
            pilots = [k for k, _ in PILOTS]
            return planes.index(data.get("aviao", "dart")), pilots.index(data.get("piloto", "riding"))
        except (OSError, ValueError, TypeError, AttributeError):
            return 0, 1  # Jato Alongado com o boneco montado

    def save_selection(self) -> None:
        path = user_data_dir() / CONFIG_FILENAME
        try:
            path.write_text(
                json.dumps({"aviao": self.plane_key, "piloto": self.pilot_key, "cores": self.plane_colors,
                            "padroes": self.plane_patterns, "controle": self.control_mode},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def start_run(self) -> None:
        self.save_selection()
        self.reset()
        self.cheat_invincible = self.cheat_armed       # precisa ser digitado de novo a cada partida
        self.cheat_armed = False
        self.cheat_keys.clear()
        self.state = "playing"
        self.plane_surface()              # já monta a pintura do voo (evita um tranco no 1º quadro)
        self.start_maneuver(START_MANEUVER)
        self.ensure_webcam()

    # --------------------------------------------------------------- manobras
    def start_maneuver(self, name: Optional[str]) -> None:
        """Começa uma manobra (substitui a atual). Só muda o desenho do avião."""
        if name in MANEUVER_STYLES:
            self.maneuver = name
            self.maneuver_time = 0.0

    def update_maneuver(self, dt: float) -> None:
        if self.maneuver is None:
            return
        self.maneuver_time += dt
        if self.maneuver_time >= MANEUVER_STYLES[self.maneuver].duration:
            self.maneuver = None
            self.maneuver_time = 0.0

    def maneuver_pose(self) -> Optional[Tuple[float, float, float, float, float]]:
        """(roll, pitch, dx, dy, dz) da manobra atual, interpolados no tempo; None sem manobra."""
        if self.maneuver is None:
            return None
        rows = self.maneuver_curves[self.maneuver]
        u = clamp(self.maneuver_time / MANEUVER_STYLES[self.maneuver].duration, 0.0, 1.0)
        for j in range(1, len(rows)):
            if u <= rows[j][0] or j == len(rows) - 1:
                a, b = rows[j - 1], rows[j]
                f = clamp((u - a[0]) / max(1e-6, b[0] - a[0]), 0.0, 1.0)
                return tuple(a[k] + (b[k] - a[k]) * f for k in range(1, 6))  # type: ignore[return-value]
        return None

    # ------------------------------------------------------------------ estado
    def reset(self) -> None:
        self.restoration = 5.0
        self.trash_cleaned = 0
        self.combo = 1
        self.combo_timer = 0.0
        self.streak = 0
        self.speed = BASE_SPEED
        self.game_over = False
        self.paused = False
        self.elapsed = 0.0
        self.distance_travelled = 0.0
        self.player_x = 0.0
        self.player_y = START_ALTITUDE
        self.player_vx = 0.0
        self.player_vy = 0.0
        self.roll = 0.0
        self.cam_x = 0.0
        self.held: set = set()
        self.pressed_keys: set = set()
        self.show_hitboxes = False
        self.lives = 3
        self.maneuver: Optional[str] = None
        self.maneuver_time = 0.0
        self.shield_timer = 0.0
        self.magnet_timer = 0.0
        self.invulnerable_timer = 0.0
        self.hit_flash_timer = 0.0
        self.segments: List[float] = []
        self.entities: List[Entity] = []
        self.beams: List[Beam] = []
        self.floating: List[FloatingText] = []
        self.high_score_dirty = False
        self.high_score_save_timer = 0.0
        self.spawn_counter = 0
        self.trash_counter = 0
        self.obstacle_counters = {kind: 0 for kind in OBSTACLE_KINDS}
        self.next_spawn_z = 520.0
        self.init_world()

    def current_stage(self) -> Stage:
        for stage in reversed(STAGES):
            if self.restoration >= stage.min_value:
                return stage
        return STAGES[0]

    def visual_stage_pair(self) -> Tuple[Stage, Stage, float]:
        value = self.restoration
        for i in range(len(STAGES) - 1):
            a, b = STAGES[i], STAGES[i + 1]
            if a.min_value <= value < b.min_value:
                return a, b, (value - a.min_value) / (b.min_value - a.min_value)
        return STAGES[-1], STAGES[-1], 1.0

    def increase_restoration(self, amount: float) -> None:
        self.restoration = clamp(self.restoration + amount, 0.0, 100.0)

    def collect_trash(self, entity: Entity) -> None:
        if entity.collected:
            return
        entity.collected = True
        value = 15 * self.combo
        self.trash_cleaned += value
        self.increase_restoration(2.1 + (0.25 if self.combo >= 4 else 0.0))
        self.streak += 1
        self.combo_timer = 2.2
        if self.streak % 4 == 0:
            self.combo = min(8, self.combo + 1)
        self.beams.append(Beam(entity.x, entity.z))
        self.floating.append(FloatingText(f"+{value}", entity.x, entity.y + 35.0))
        if self.trash_cleaned > self.high_score:
            self.high_score = self.trash_cleaned
            self.high_score_dirty = True

    @staticmethod
    def load_high_score() -> int:
        # Lê a pasta de dados e, por compatibilidade, o arquivo antigo ao lado
        # do script; fica com o maior valor encontrado.
        paths = [save_file_path(), *legacy_save_paths()]
        return max(_read_record(path) for path in paths)

    def save_high_score(self) -> None:
        if self.trash_cleaned > self.high_score:
            self.high_score = self.trash_cleaned
            self.high_score_dirty = True
        if not self.high_score_dirty:
            return
        save_path = save_file_path()
        temp_path = save_path.with_suffix(".tmp")
        try:
            temp_path.write_text(
                json.dumps({"recorde": self.high_score}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temp_path.replace(save_path)
            self.high_score_dirty = False
            self.high_score_save_timer = 0.0
        except OSError:
            # A pasta pode estar somente para leitura; o jogo segue normalmente
            # e só tenta de novo após o intervalo.
            self.high_score_save_timer = 0.0

    def collect_powerup(self, entity: Entity) -> None:
        if entity.collected:
            return
        entity.collected = True
        if entity.kind == "shield":
            self.shield_timer = max(self.shield_timer, 6.0)
            label = "ESCUDO"
        elif entity.kind == "magnet":
            self.magnet_timer = max(self.magnet_timer, 7.0)
            label = "IMÃ"
        else:  # repair
            if self.lives < 3:
                self.lives += 1
                label = "+1 VIDA"
            else:
                self.increase_restoration(3.0)
                label = "+3% ECO"
        self.floating.append(FloatingText(label, entity.x, entity.y + 48.0))
        self.start_maneuver(POWERUP_MANEUVERS.get(entity.kind))

    def take_hit(self) -> None:
        if self.cheat_invincible or self.shield_timer > 0 or self.invulnerable_timer > 0:
            return
        self.lives = max(0, self.lives - 1)
        self.invulnerable_timer = 1.25
        self.hit_flash_timer = 0.28
        self.combo = 1
        self.streak = 0
        self.combo_timer = 0.0
        if self.lives == 0:
            self.game_over = True
            self.clear_input()
            self.save_high_score()

    def update_combo(self, dt: float) -> None:
        if self.combo_timer > 0:
            self.combo_timer -= dt
        elif self.combo > 1:
            self.combo = 1
            self.streak = 0

    # ------------------------------------------------------------------ mundo
    def init_world(self) -> None:
        self.segments = [float(z) for z in range(100, 2501, 100)]
        self.segment_base = 0           # índice absoluto de segments[0] na pista
        self.entities.clear()
        self.next_spawn_z = 520.0
        while self.next_spawn_z <= 2500:
            self.spawn_pattern(self.next_spawn_z)
            self.next_spawn_z += random.choice([100.0, 120.0, 140.0])

    def next_obstacle(self, kind: str) -> str:
        """Modelos de cada tipo aparecem sempre na mesma ordem (não sorteados)."""
        options = OBSTACLE_SPECS[kind]
        sprite = options[self.obstacle_counters[kind] % len(options)].sprite
        self.obstacle_counters[kind] += 1
        return sprite

    def spawn_pattern(self, z: float) -> None:
        self.spawn_counter += 1
        trash_lane = random.choice([-1, 0, 1])
        trash_y = random.choice(TRASH_HEIGHTS)
        self.entities.append(Entity(z, trash_lane, "trash", trash_y, TRASH_MODELS[self.trash_counter % len(TRASH_MODELS)]))
        self.trash_counter += 1

        available = [-1, 0, 1]
        available.remove(trash_lane)
        if random.random() < 0.45:
            self.entities.append(Entity(z + 45, random.choice(available), "trash", random.choice(TRASH_HEIGHTS),
                                        TRASH_MODELS[self.trash_counter % len(TRASH_MODELS)]))
            self.trash_counter += 1

        difficulty = clamp(self.elapsed / 180.0, 0.0, 1.0)
        obstacle_probability = 0.35 + difficulty * 0.30
        if random.random() < obstacle_probability and available:
            obstacle_lane = random.choice(available)
            roll = random.random()
            kind = "low" if roll < 0.45 else ("gate" if roll < 0.75 else "tower")
            self.entities.append(Entity(z, obstacle_lane, kind, 0.0, self.next_obstacle(kind)))

        if random.random() < 0.13:
            powerup_lane = random.choice([-1, 0, 1])
            powerup_kind = random.choice(list(POWERUP_KINDS))
            self.entities.append(Entity(z + 30.0, powerup_lane, powerup_kind, random.choice(TRASH_HEIGHTS)))

    def mid_cam(self) -> float:
        """Deslocamento da câmera da camada média (construções e árvores)."""
        return self.cam_x * MID_PARALLAX

    def project(self, x: float, y: float, z: float,
                cam: Optional[float] = None) -> Tuple[float, float, float]:
        z = max(20.0, z)
        scale = FOV / z
        if cam is None:
            cam = self.cam_x
        sx = WIDTH / 2 + (x - cam) * scale
        sy = HORIZON_Y + (155.0 - y) * scale
        return sx, sy, scale

    # ---------------------------------------------------------------- entrada
    FLIGHT_KEYS = {
        pygame.K_LEFT: "left", pygame.K_a: "left",
        pygame.K_RIGHT: "right", pygame.K_d: "right",
        pygame.K_UP: "up", pygame.K_w: "up", pygame.K_SPACE: "up",
        pygame.K_DOWN: "down", pygame.K_s: "down",
    }

    # ------------------------------------------------------ controle pela câmera
    def toggle_control_mode(self) -> None:
        """V no hangar: teclado → corpo → uma mão → teclado."""
        index = CONTROL_MODES.index(self.control_mode)
        self.control_mode = CONTROL_MODES[(index + 1) % len(CONTROL_MODES)]
        self.stop_webcam()                              # cada modo calibra do zero
        self.ensure_webcam()

    @property
    def uses_camera(self) -> bool:
        return self.control_mode in ("camera", "mao")

    def ensure_webcam(self) -> None:
        """Liga a webcam se um controle por câmera estiver escolhido (uma vez só)."""
        if not self.uses_camera or self.webcam is not None:
            return
        mode = "mao" if self.control_mode == "mao" else "corpo"
        self.webcam = WebcamControl(PoseCameraSource(find_pose_model()), mode=mode)
        self.webcam.start()

    def stop_webcam(self) -> None:
        if self.webcam is not None:
            self.webcam.stop()
            self.webcam = None
        self.analog = (0.0, 0.0)
        self.webcam_surface = None
        self.webcam_surface_bytes = None

    def poll_webcam(self) -> None:
        """Lê a câmera (se estiver ligada) e atualiza os eixos e a miniatura."""
        if self.webcam is None:
            self.analog = (0.0, 0.0)
            return
        self.webcam.poll()
        self.analog = self.webcam.axes()
        preview = self.webcam.preview
        if preview is not None and preview is not self.webcam_surface_bytes:
            self.webcam_surface_bytes = preview
            self.webcam_surface = pygame.image.frombytes(preview, (160, 120), "RGB")

    def webcam_hangar_status(self) -> str:
        if not self.uses_camera:
            return "Controle: teclado   (V: trocar o controle)"
        label = CONTROL_LABELS[self.control_mode]
        if self.webcam is None or self.webcam.error:
            reason = self.webcam.error if self.webcam is not None else "câmera desligada"
            return f"Câmera indisponível ({reason}): usando o teclado   (V: trocar o controle)"
        if not self.webcam.receiving:
            return f"Controle: {label}, iniciando...   (V: trocar o controle)"
        hand = self.control_mode == "mao"
        if not self.webcam.calibrated:
            what = ("mantenha a mão parada na posição de repouso" if hand
                    else "fique parado de frente para a câmera")
            return f"Câmera ({label}): calibrando, {what} ({int(self.webcam.progress * 100)}%)"
        if self.webcam.tracked_visible:
            return f"Câmera ({label}): " + ("mão detectada" if hand else "pessoa detectada")
        return f"Câmera ({label}): " + ("mostre a mão para a câmera" if hand else "fique na frente da câmera")

    def draw_webcam_overlay(self) -> None:
        """Calibração, falhas e miniatura da câmera durante o voo."""
        if not self.uses_camera:
            return
        hand = self.control_mode == "mao"
        if self.webcam is not None and self.webcam_surface is not None:
            frame = self.webcam_surface.get_rect(bottomleft=(12, HEIGHT - 12))
            self.screen.blit(self.webcam_surface, frame)
            pygame.draw.rect(self.screen, rgb("c5e1c7"), frame, 1)
        if self.webcam is None or self.webcam.error:
            reason = self.webcam.error if self.webcam is not None else "câmera desligada"
            text = self.small_font.render(f"Câmera indisponível ({reason}): voando com o teclado",
                                          True, rgb("ffab91"))
            self.screen.blit(text, text.get_rect(center=(WIDTH // 2, 170)))
            return
        if not self.webcam.calibrated:
            panel = pygame.Rect(WIDTH // 2 - 260, 150, 520, 92)
            pygame.draw.rect(self.screen, (12, 24, 18, 225), panel, border_radius=10)
            pygame.draw.rect(self.screen, rgb("fff59d"), panel, 2, border_radius=10)
            if hand:
                hint = ("Mantenha a mão parada na posição de repouso" if self.webcam.tracked_visible
                        else "Mostre a mão para a câmera")
            else:
                hint = ("Fique parado, de frente para a câmera" if self.webcam.tracked_visible
                        else "Entre no quadro da câmera")
            title = self.font.render(f"CALIBRANDO: {hint}", True, (255, 255, 255))
            self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 178)))
            bar = pygame.Rect(panel.x + 30, panel.bottom - 28, panel.width - 60, 12)
            pygame.draw.rect(self.screen, (40, 52, 46), bar, border_radius=6)
            fill = bar.copy()
            fill.width = int(bar.width * self.webcam.progress)
            pygame.draw.rect(self.screen, rgb("fff59d"), fill, border_radius=6)
            return
        if not self.webcam.tracked_visible:
            text = self.small_font.render(
                "Não estou vendo sua mão: volte ela para o quadro da câmera" if hand
                else "Não estou vendo você: volte para o quadro da câmera",
                                          True, rgb("ffab91"))
            self.screen.blit(text, text.get_rect(center=(WIDTH // 2, 170)))

    WEBCAM_DIRECTION_KEYS = {"left": pygame.K_LEFT, "right": pygame.K_RIGHT,
                             "up": pygame.K_UP, "down": pygame.K_DOWN}

    def apply_webcam_menu(self) -> None:
        """Transforma os gestos da câmera em teclas nos menus e na tela de fim de jogo.

        Os eventos são consumidos a cada quadro, mesmo no voo, para não acumular
        gestos feitos durante a partida.
        """
        if self.webcam is None:
            return
        for event in self.webcam.take_events():
            if self.control_mode == "mao":
                key = self.hand_gesture_key(event)
            else:
                key = self.body_gesture_key(event)
            if key is not None:
                self.handle_key(key)

    def body_gesture_key(self, event: str) -> Optional[int]:
        """Modo corpo: inclinar = setas; mão direita confirma; mão esquerda = Oficina/cancelar/hangar."""
        if self.state in ("menu", "paint"):
            if event == "right_hand":
                return pygame.K_RETURN                        # decolar ou salvar
            if event == "left_hand":
                return pygame.K_ESCAPE if self.state == "paint" else pygame.K_c
            return self.WEBCAM_DIRECTION_KEYS.get(event)
        if self.state == "playing" and self.game_over:
            return {"right_hand": pygame.K_RETURN, "left_hand": pygame.K_c}.get(event)
        return None

    def hand_gesture_key(self, event: str) -> Optional[int]:
        """Modo uma mão: lados = setas; cima = piloto/linha; baixo = Oficina/cancelar/hangar;
        mão levantada = decolar, salvar ou voar de novo."""
        if self.state == "menu":
            return {"left": pygame.K_LEFT, "right": pygame.K_RIGHT, "up": pygame.K_DOWN,
                    "down": pygame.K_c, "raised": pygame.K_RETURN}.get(event)
        if self.state == "paint":
            if event == "up":                                 # alterna a linha de cores e a de padrões
                return pygame.K_UP if self.paint_row == 1 else pygame.K_DOWN
            return {"left": pygame.K_LEFT, "right": pygame.K_RIGHT,
                    "down": pygame.K_ESCAPE, "raised": pygame.K_RETURN}.get(event)
        if self.state == "playing" and self.game_over:
            return {"raised": pygame.K_RETURN, "down": pygame.K_c}.get(event)
        return None

    def handle_key(self, key: int) -> None:
        if self.state == "menu":
            self.handle_menu_key(key)
            return
        if self.state == "paint":
            self.handle_paint_key(key)
            return
        if self.game_over:
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                self.start_run()
            elif key in (pygame.K_c, pygame.K_TAB):
                self.state = "menu"
            return
        if key == pygame.K_x and self.cheat_invincible:
            self.cheat_invincible = False
            self.cheat_flash = CHEAT_FLASH_TIME
            return
        if key == pygame.K_F3:
            self.show_hitboxes = not self.show_hitboxes
            return
        if key in (pygame.K_ESCAPE, pygame.K_p):
            self.paused = not self.paused
            if self.paused:
                self.clear_input()
            else:
                self.resync_input()
            return
        if self.paused:
            if key in (pygame.K_c, pygame.K_TAB):
                self.paused = False
                self.state = "menu"
            return
        if key in self.FLIGHT_KEYS:
            self.pressed_keys.add(key)
            self.held = {self.FLIGHT_KEYS[k] for k in self.pressed_keys}

    def handle_key_up(self, key: int) -> None:
        if key in self.FLIGHT_KEYS:
            self.pressed_keys.discard(key)
            # Soltar UP com W ainda pressionado mantém a subida.
            self.held = {self.FLIGHT_KEYS[k] for k in self.pressed_keys}

    def clear_input(self) -> None:
        self.pressed_keys.clear()
        self.held.clear()

    def resync_input(self) -> None:
        """Ao voltar da pausa, retoma as teclas que continuam pressionadas."""
        self.clear_input()
        try:
            pressed = pygame.key.get_pressed()
            self.pressed_keys = {k for k in self.FLIGHT_KEYS if pressed[k]}
        except (pygame.error, IndexError):
            return
        self.held = {self.FLIGHT_KEYS[k] for k in self.pressed_keys}

    def feed_cheat(self, key: int) -> bool:
        """Guarda as últimas teclas do hangar. True quando a sequência completa (a tecla é consumida)."""
        self.cheat_keys.append(key)
        del self.cheat_keys[:-len(CHEAT_CODE)]
        if tuple(self.cheat_keys) == CHEAT_CODE:
            self.cheat_keys.clear()
            self.cheat_armed = True
            self.cheat_flash = CHEAT_FLASH_TIME
            return True
        return False

    def handle_menu_key(self, key: int) -> None:
        if self.feed_cheat(key):
            return
        if key in (pygame.K_LEFT, pygame.K_a):
            self.plane_index = (self.plane_index - 1) % len(PLANE_MODELS)
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self.plane_index = (self.plane_index + 1) % len(PLANE_MODELS)
        elif key in (pygame.K_UP, pygame.K_w):
            self.pilot_index = (self.pilot_index - 1) % len(PILOTS)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.pilot_index = (self.pilot_index + 1) % len(PILOTS)
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            self.start_run()
        elif key == pygame.K_c:
            self.open_paint_shop()
        elif key == pygame.K_v:
            self.toggle_control_mode()
        elif key == pygame.K_r and self.webcam is not None:
            self.webcam.restart_calibration()           # recalibra a posição de repouso

    # ------------------------------------------------------ oficina de pintura
    def open_paint_shop(self) -> None:
        self.paint_before = self.plane_color_key
        self.pattern_before = self.plane_pattern_key
        self.paint_index = PLANE_COLOR_KEYS.index(self.paint_before)
        self.pattern_index = PLANE_PATTERN_KEYS.index(self.pattern_before)
        self.paint_row = 1 if self.pattern_before != "liso" else 0
        self.state = "paint"

    def set_paint_index(self, index: int) -> None:
        """Muda a cor do avião atual na hora (prévia ao vivo). Escolher cor volta ao padrão liso."""
        self.paint_index = index % len(PLANE_COLORS)
        self.plane_colors[self.plane_key] = PLANE_COLOR_KEYS[self.paint_index]
        self.set_pattern_index(0)

    def set_pattern_index(self, index: int) -> None:
        """Muda o padrão de pintura do avião atual na hora (prévia ao vivo)."""
        self.pattern_index = index % len(PLANE_PATTERNS)
        self.plane_patterns[self.plane_key] = PLANE_PATTERN_KEYS[self.pattern_index]

    def handle_paint_key(self, key: int) -> None:
        step = 0
        if key in (pygame.K_LEFT, pygame.K_a):
            step = -1
        elif key in (pygame.K_RIGHT, pygame.K_d):
            step = 1
        elif key in (pygame.K_UP, pygame.K_w):
            self.paint_row = 0             # linha das cores
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.paint_row = 1             # linha dos padrões
        elif key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_c):
            self.save_selection()          # confirma: cor e padrão ficam salvos para este avião
            self.state = "menu"
        elif key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            self.plane_colors[self.plane_key] = self.paint_before      # cancela
            self.plane_patterns[self.plane_key] = self.pattern_before
            self.state = "menu"
        if step and self.paint_row == 0:
            self.set_paint_index(self.paint_index + step)
        elif step:
            self.set_pattern_index(self.pattern_index + step)

    # ------------------------------------------------------------- colisões
    def get_player_hitbox(self) -> Hitbox:
        half_w = PLANE_WIDTH * 0.42      # colisão um pouco menor que o desenho (mais justo)
        half_h = PLANE_HEIGHT * 0.5
        return Hitbox(self.player_x - half_w, self.player_x + half_w,
                      self.player_y - half_h, self.player_y + half_h,
                      PLAYER_Z - 27.0, PLAYER_Z + 27.0)

    def get_entity_hitbox(self, entity: Entity) -> Hitbox:
        x = entity.x
        if entity.kind == "trash" or entity.kind in POWERUP_KINDS:
            r = 30.0 if entity.kind == "trash" else 28.0
            return Hitbox(x - r, x + r, entity.y - r, entity.y + r, entity.z - 18.0, entity.z + 18.0)
        if entity.kind in OBSTACLE_KINDS:
            spec = obstacle_spec(entity)
            return Hitbox(x - spec.width / 2, x + spec.width / 2, spec.y_min, spec.y_max, entity.z - 16.0, entity.z + 16.0)
        return Hitbox(x, x, 0.0, 0.0, entity.z, entity.z)

    def hitbox_screen_rect(self, box: Hitbox) -> pygame.Rect:
        z = max(20.0, (box.z_min + box.z_max) / 2)
        x0, y0, _ = self.project(box.x_min, min(box.y_max, 330.0), z)
        x1, y1, _ = self.project(box.x_max, box.y_min, z)
        return pygame.Rect(int(x0), int(y0), max(1, int(x1 - x0)), max(1, int(y1 - y0)))

    # ------------------------------------------------------------- simulação
    def update_flight(self, dt: float) -> None:
        ax, ay = self.analog
        ix = clamp((1 if "right" in self.held else 0) - (1 if "left" in self.held else 0) + ax, -1.0, 1.0)
        iy = clamp((1 if "up" in self.held else 0) - (1 if "down" in self.held else 0) + ay, -1.0, 1.0)
        response = 1.0 - math.exp(-FLIGHT_RESPONSE * dt)
        self.player_vx += (ix * MAX_LATERAL_SPEED - self.player_vx) * response
        self.player_vy += (iy * MAX_VERTICAL_SPEED - self.player_vy) * response
        self.player_x += self.player_vx * dt
        self.player_y += self.player_vy * dt
        if abs(self.player_x) > MAX_PLAYER_X:
            self.player_x = clamp(self.player_x, -MAX_PLAYER_X, MAX_PLAYER_X)
            self.player_vx = 0.0
        if not MIN_ALTITUDE <= self.player_y <= MAX_ALTITUDE:
            self.player_y = clamp(self.player_y, MIN_ALTITUDE, MAX_ALTITUDE)
            self.player_vy = 0.0
        target_roll = -self.player_vx / MAX_LATERAL_SPEED * MAX_ROLL_DEG
        self.roll += (target_roll - self.roll) * response
        cam_target = self.player_x * CAMERA_FOLLOW
        self.cam_x += (cam_target - self.cam_x) * response

    def update(self, dt: float) -> None:
        self.poll_webcam()
        self.apply_webcam_menu()
        self.cheat_flash = max(0.0, self.cheat_flash - dt)
        if self.state != "playing" or self.game_over or self.paused:
            return
        dt = min(dt, MAX_DT)
        self.elapsed += dt
        self.high_score_save_timer += dt
        self.shield_timer = max(0.0, self.shield_timer - dt)
        self.magnet_timer = max(0.0, self.magnet_timer - dt)
        self.invulnerable_timer = max(0.0, self.invulnerable_timer - dt)
        self.hit_flash_timer = max(0.0, self.hit_flash_timer - dt)
        self.update_maneuver(dt)
        difficulty = clamp(self.elapsed / 180.0, 0.0, 1.0)
        self.speed = (BASE_SPEED + self.restoration * RESTORATION_SPEED_GAIN
                      + difficulty * DIFFICULTY_SPEED_GAIN)
        self.distance_travelled += self.speed * dt
        self.update_combo(dt)
        self.update_flight(dt)

        for i in range(len(self.segments)):
            self.segments[i] -= self.speed * dt

        # Mantém um trecho de pista entre a câmera e o primeiro segmento
        # (antes ficava uma faixa sem pista na parte de baixo da tela).
        while self.segments and self.segments[0] < -40:
            self.segments.pop(0)
            self.segment_base += 1
            last = self.segments[-1] if self.segments else 100.0
            new_z = last + 100.0
            self.segments.append(new_z)
            self.spawn_pattern(new_z + 20.0)

        player_hitbox = self.get_player_hitbox()
        for entity in self.entities:
            entity.z -= self.speed * dt
            if entity.collected:
                continue
            overlaps = player_hitbox.intersects(self.get_entity_hitbox(entity))
            if entity.kind in POWERUP_KINDS and overlaps:
                self.collect_powerup(entity)
            elif entity.kind == "trash":
                magnet_reaches = (
                    self.magnet_timer > 0
                    and abs(entity.z - PLAYER_Z) <= 45.0
                    and abs(self.player_x - entity.x) < LANE_WIDTH * 1.1
                    and abs(self.player_y - entity.y) < 110.0
                )
                if overlaps or magnet_reaches:
                    self.collect_trash(entity)
            elif overlaps:
                self.take_hit()
                if self.game_over:
                    break

        # Remove o que já passou pelo avião (não cobre a visão do jogador).
        self.entities = [e for e in self.entities if e.z > PLAYER_Z - 70.0 and not e.collected]
        for beam in self.beams:
            beam.z -= self.speed * dt
            beam.ttl -= dt
        self.beams = [b for b in self.beams if b.ttl > 0]
        for text in self.floating:
            text.y += 48.0 * dt
            text.ttl -= dt
        self.floating = [text for text in self.floating if text.ttl > 0]
        if self.high_score_dirty and self.high_score_save_timer >= HIGH_SCORE_SAVE_INTERVAL:
            self.save_high_score()

    # ------------------------------------------------------------- desenho
    def blit_world_sprite(self, sprite: pygame.Surface, key: tuple, x: float, y: float, z: float,
                          height: float, flip: bool = False, cam: Optional[float] = None) -> None:
        if z < NEAR_CLIP_Z:
            return  # colado na câmera: ficaria gigante (e caro) sem acrescentar nada
        sx, sy, scale = self.project(x, y, z, cam)
        screen_h = max(2, int(height * scale))
        if screen_h > HEIGHT * 2:
            return
        if screen_h < 100:
            screen_h -= screen_h % 2   # objetos pequenos/distantes: menos reescalas, diferença invisível
        aspect = sprite.get_width() / max(1, sprite.get_height())
        screen_w = max(2, int(screen_h * aspect))
        left = int(sx) - screen_w // 2
        top = int(sy) - screen_h
        if left > WIDTH or left + screen_w < 0 or top > HEIGHT or top + screen_h < 0:
            return  # fora da tela: não reescala nem desenha
        level = self.fog_level(z)
        if level >= FOG_LEVELS:
            return  # totalmente dentro da neblina
        size = (screen_w, screen_h)
        scaled = self.scaled_sprite(sprite, key, size, flip)
        if level > 0:
            scaled = self.fogged_sprite(scaled, (key, size, flip), level)
        self.screen.blit(scaled, (left, top))

    def draw_tree(self, seq: int, side: int, x: float, z: float, size: float, cam: float) -> None:
        """Árvore Solarpunk nas margens: modelo da pasta ou desenho de reserva."""
        if z < NEAR_CLIP_Z:
            return
        if self.tree_sprites:
            offset = len(SOLARPUNK_TREE_SPECS) // 2 if side > 0 else 0
            name, height = SOLARPUNK_TREE_SPECS[(seq + offset) % len(SOLARPUNK_TREE_SPECS)]
            sprite = self.tree_sprites.get(name)
            if sprite is not None:
                self.blit_world_sprite(sprite, ("tree", name), side * x, 0, z, height * size, side > 0, cam=cam)
                return
        if self.fog_level(z) >= FOG_LEVELS:
            return
        x, y, scale = self.project(side * x, 0, z, cam)
        scale *= size
        trunk_w = max(3, int(26 * scale))
        trunk_h = max(6, int(200 * scale))
        x0, y0 = int(x), int(y)
        points = []
        steps = 5
        for s in range(steps + 1):
            t = s / steps
            offset_x = math.sin(t * math.pi) * (18 * scale) * side
            points.append((x0 + offset_x, y0 - (trunk_h * t)))
        pygame.draw.lines(self.screen, (141, 110, 99), False, points, trunk_w)
        pygame.draw.lines(self.screen, (255, 213, 79), False, points, max(1, int(3 * scale)))
        top_x, top_y = points[-1]
        canopy_r = max(8, int(75 * scale))
        pygame.draw.circle(self.screen, (0, 230, 118), (int(top_x), int(top_y)), canopy_r)
        pygame.draw.circle(self.screen, (41, 182, 246), (int(top_x), int(top_y)), int(canopy_r * 0.65))
        pygame.draw.circle(self.screen, (255, 213, 79), (int(top_x), int(top_y)), canopy_r, max(1, int(3 * scale)))

    def scenery_sprite(self, name: str) -> Optional[pygame.Surface]:
        return self.scenario_sprites.get(name) or self.side_prop_sprites.get(name)

    def draw_industrial(self, specs: List[Tuple[str, float]], seq: int, side: int, x: float,
                        z: float, cam: float, fallback: bool) -> None:
        """Peça industrial das margens, na ordem fixa da lista (sem sorteio)."""
        if z < NEAR_CLIP_Z:
            return
        offset = len(specs) // 2 if side > 0 else 0
        for step in range(len(specs)):
            name, height = specs[(seq + offset + step) % len(specs)]
            sprite = self.scenery_sprite(name)
            if sprite is not None:
                self.blit_world_sprite(sprite, ("scenery", name), side * x, 0, z, height, side > 0, cam=cam)
                return
        if not fallback or self.fog_level(z) >= FOG_LEVELS:
            return
        sx, sy, scale = self.project(side * x, 0, z, cam)
        width = max(2, int(95 * scale))
        height = max(2, int(250 * scale))
        body = lerp_color(rgb("26201d") if self.restoration < 25 else rgb("191c26"), self.fog_color,
                          self.fog_level(z) / FOG_LEVELS)
        pygame.draw.rect(self.screen, body, (int(sx - width / 2), int(sy - height), width, height))

    def draw_margins(self, seg: int, z: float, wave_z: float) -> None:
        """Duas fileiras por lado em cada trecho da pista: fundo (z) e borda (z + 50)."""
        green = self.restoration >= 50.0
        mid_cam = self.mid_cam()
        margin_cam = self.cam_x * MARGIN_PARALLAX
        border_z = z + 50.0
        for side in (-1, 1):
            if green and z <= wave_z:
                self.draw_tree(seg, side, MID_ROW_X, z, 1.0, mid_cam)
            else:
                self.draw_industrial(MID_ROW_SPECS, seg, side, MID_ROW_X, z, mid_cam, fallback=seg % 2 == 0)
            if border_z > MARGIN_MAX_Z:
                continue   # peças pequenas da borda: invisíveis tão longe, na neblina
            if (seg + (side > 0)) % 2:
                continue   # borda alterna de lado a cada trecho: menos peças, mesma continuidade
            if green and border_z <= wave_z:
                self.draw_tree(seg + 3, side, MARGIN_X, border_z, 0.45, margin_cam)
            else:
                self.draw_industrial(MARGIN_PROP_SPECS, seg // 2, side, MARGIN_X, border_z, margin_cam,
                                     fallback=False)

    def draw_world(self) -> None:
        a, b, t = self.visual_stage_pair()
        fog = self.fog_color
        water_base = lerp_color(a.water, b.water, t)
        road_even = lerp_color(a.road_even, b.road_even, t)
        road_odd = lerp_color(a.road_odd, b.road_odd, t)
        lane_base = lerp_color(a.lane_line, b.lane_line, t)
        purified_road = lerp_color(road_even, rgb("8bcf78"), 0.2)
        wave_z = 180.0 + (self.restoration / 100.0) ** 1.15 * 2150.0

        green = self.restoration >= GRASS_START_RESTORATION
        # Com as duas texturas, o chão inteiro é coberto por elas (concreto/grama).
        textured_ground = self.concrete_texture is not None and (self.grass_texture is not None or not green)
        stretches = []
        for i, z in reversed(list(enumerate(self.segments))):
            seg = self.segment_base + i   # posição fixa do trecho na pista (não muda ao reciclar)
            next_z = z + 100.0
            left1 = self.project(-ROAD_WIDTH / 2, 0, z)
            right1 = self.project(ROAD_WIDTH / 2, 0, z)
            left2 = self.project(-ROAD_WIDTH / 2, 0, next_z)
            right2 = self.project(ROAD_WIDTH / 2, 0, next_z)
            haze = clamp((z + 50.0 - FOG_START) / (FOG_END - FOG_START), 0.0, 1.0)
            if not textured_ground:
                # 1ª passada (sem texturas): chão de cada trecho em cores lisas.
                ground = GRASS_FALLBACK[seg % 2] if green and z <= wave_z else water_base
                pygame.draw.polygon(self.screen, lerp_color(ground, fog, haze),
                                    [(0, left2[1]), (WIDTH, right2[1]), (WIDTH, right1[1]), (0, left1[1])])
            stretches.append((seg, z, next_z, left1, right1, left2, right2, haze))

        # 2ª passada: chão com textura (concreto sujo e, onde já foi restaurado, grama).
        self.draw_ground(wave_z)

        # 3ª passada: pista, faixas e margens, do fundo para a frente.
        for seg, z, next_z, left1, right1, left2, right2, haze in stretches:
            purified = z <= wave_z
            base_color = purified_road if purified else (road_even if seg % 2 == 0 else road_odd)
            local_color = lerp_color(base_color, fog, haze)
            lane_line = lerp_color(lane_base, fog, haze)
            pygame.draw.polygon(self.screen, local_color, [(left1[0], left1[1]), (right1[0], right1[1]), (right2[0], right2[1]), (left2[0], left2[1])])

            for divider in (-0.5, 0.5):
                p1 = self.project(LANE_WIDTH * divider, 0, z)
                p2 = self.project(LANE_WIDTH * divider, 0, next_z)
                pygame.draw.line(self.screen, lane_line, (p1[0], p1[1]), (p2[0], p2[1]), max(1, int(4 * p1[2])))

            self.draw_margins(seg, z, wave_z)

    def draw_ground_shadow(self, x: float, y: float, z: float, width: float, alpha: int) -> None:
        alpha = int(alpha * (1.0 - self.fog_level(z) / FOG_LEVELS))
        if alpha <= 2:
            return
        sx, sy, scale = self.project(x, 0, z)
        w = max(4, int(width * scale))
        h = max(2, int(w * 0.18))
        key = (w, h, alpha // 4)
        shadow = self.shadow_cache.get(key)
        if shadow is None:
            if len(self.shadow_cache) > 400:
                self.shadow_cache.pop(next(iter(self.shadow_cache)))
            shadow = pygame.Surface((w, h), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (0, 0, 0, alpha // 4 * 4), shadow.get_rect())
            self.shadow_cache[key] = shadow
        self.screen.blit(shadow, shadow.get_rect(center=(int(sx), int(sy))))

    def draw_entity(self, entity: Entity, wave_z: float) -> None:
        x, y, scale = self.project(entity.x, entity.y, entity.z)
        scale = max(0.08, scale)
        purified = entity.z <= wave_z
        if entity.kind == "trash":
            self.draw_ground_shadow(entity.x, entity.y, entity.z, 50, 70)
            sprite = self.trash_sprites.get(entity.sprite)
            if sprite is not None:
                bob = math.sin(self.elapsed * 3.0 + entity.z * 0.02) * 3
                self.blit_world_sprite(sprite, ("trash", entity.sprite), entity.x, entity.y - 23 + bob, entity.z, 46)
            else:
                radius = max(3, int(22 * scale))
                color = rgb("ffb300") if purified else rgb("bf360c")
                pygame.draw.circle(self.screen, color, (int(x), int(y)), radius)
                pygame.draw.circle(self.screen, rgb("00e676"), (int(x), int(y)), radius, max(1, int(3 * scale)))
        elif entity.kind in POWERUP_KINDS:
            self.draw_ground_shadow(entity.x, entity.y, entity.z, 46, 60)
            sprite = self.powerup_sprites.get(entity.kind)
            if sprite is not None:
                bob = math.sin(self.elapsed * 3.2 + entity.z * 0.015) * 4
                self.blit_world_sprite(sprite, ("powerup", entity.kind), entity.x, entity.y - 26 + bob, entity.z, 56)
            else:
                radius = max(5, int(20 * scale))
                color = {"shield": rgb("40c4ff"), "magnet": rgb("ab47bc"), "repair": rgb("ffd54f")}[entity.kind]
                pygame.draw.circle(self.screen, color, (int(x), int(y)), radius)
                pygame.draw.circle(self.screen, rgb("fff8e1"), (int(x), int(y)), radius, max(1, int(2 * scale)))
        elif entity.kind in OBSTACLE_KINDS:
            spec = obstacle_spec(entity)
            sprite = self.side_prop_sprites.get(spec.sprite)
            if sprite is not None:
                self.blit_world_sprite(sprite, ("obstacle", spec.sprite), entity.x, 0, entity.z, spec.visual_height)
            else:
                rect = self.hitbox_screen_rect(self.get_entity_hitbox(entity))
                color = {"low": rgb("5d4037"), "gate": rgb("311b92"), "tower": rgb("3e2723")}[entity.kind]
                if entity.kind == "gate":
                    pygame.draw.rect(self.screen, color, rect, max(1, int(5 * scale)))
                else:
                    pygame.draw.rect(self.screen, color, rect)

        if self.show_hitboxes:
            rect = self.hitbox_screen_rect(self.get_entity_hitbox(entity))
            color = rgb("00e676") if entity.kind == "trash" else rgb("ff1744")
            pygame.draw.rect(self.screen, color, rect, max(1, int(2 * scale)))

    def draw_entities(self, in_front: bool) -> None:
        """Desenha atrás (in_front=False) ou à frente (True) do avião."""
        wave_z = 180.0 + (self.restoration / 100.0) ** 1.15 * 2150.0
        self.entities.sort(key=lambda e: e.z, reverse=True)
        for entity in self.entities:
            if (entity.z < PLAYER_Z) == in_front:
                self.draw_entity(entity, wave_z)

    def pattern_palette(self, pattern: str) -> Optional[list]:
        """Textura do padrão como lista de 65536 pixels RGB (índice = linha * 256 + coluna)."""
        palette = self.pattern_palettes.get(pattern)
        if palette is None:
            texture = self.pattern_textures.get(pattern)
            if texture is None:
                return None
            data = pygame.image.tobytes(texture, "RGB")
            palette = [data[i:i + 3] for i in range(0, len(data), 3)]
            if len(self.pattern_palettes) >= PATTERN_CACHE_LIMIT:
                self.pattern_palettes.pop(next(iter(self.pattern_palettes)))
            self.pattern_palettes[pattern] = palette
        return palette

    def uv_index(self, menu: bool, combo: str, size: Tuple[int, int]) -> Optional[list]:
        """Para cada pixel do sprite, o índice do texel do padrão (G = linha, R = coluna)."""
        key = (menu, combo)
        index = self.uv_indices.get(key)
        if index is None:
            uv = (self.plane_menu_uv if menu else self.plane_uv).get(combo)
            if uv is None or uv.get_size() != size:
                return None
            data = pygame.image.tobytes(uv, "RGB")
            index = [(g << 8) | r for r, g in zip(data[0::3], data[1::3])]
            if len(self.uv_indices) >= 8:
                self.uv_indices.pop(next(iter(self.uv_indices)))
            self.uv_indices[key] = index
        return index

    def pattern_fill(self, menu: bool, combo: str, pattern: str, size: Tuple[int, int]) -> Optional[pygame.Surface]:
        """Imagem do padrão "vestida" no avião (mesmo tamanho do sprite), ou None se faltar algo."""
        palette = self.pattern_palette(pattern)
        index = self.uv_index(menu, combo, size) if palette is not None else None
        if palette is None or index is None:
            return None
        return pygame.image.frombytes(b"".join(map(palette.__getitem__, index)), size, "RGB")

    def plane_surface(self, menu: bool = False) -> Optional[pygame.Surface]:
        """Sprite do avião atual, já com a cor ou o padrão da Oficina de pintura aplicado ao papel."""
        sprites = self.plane_menu_sprites if menu else self.plane_sprites
        combo = self.plane_combo if self.plane_combo in sprites else f"{self.plane_key}__none"
        base = sprites.get(combo)
        color = self.plane_color
        pattern = self.plane_pattern_key
        if base is None or (color is None and pattern == "liso"):
            return base
        paint = (self.plane_menu_paint if menu else self.plane_paint).get(combo)
        if paint is None or paint.get_size() != base.get_size():
            return base
        key = (menu, combo, self.plane_color_key, pattern)
        painted = self.painted_cache.get(key)
        if painted is None:
            # Papel em branco (com a luz e as dobras) × cor ou padrão, desenhado sobre
            # o original: o piloto e as peças que não são de papel continuam como estavam.
            fill = self.pattern_fill(menu, combo, pattern, base.get_size()) if pattern != "liso" else None
            if fill is None and color is None:
                return base                # padrão sem textura/mapa UV e cor original
            layer = paint.copy()
            if fill is not None:
                layer.blit(fill, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
            else:
                layer.fill(color, special_flags=pygame.BLEND_RGB_MULT)
            painted = base.copy()
            painted.blit(layer, (0, 0))
            if len(self.painted_cache) >= 48:
                self.painted_cache.pop(next(iter(self.painted_cache)))
            self.painted_cache[key] = painted
        return painted

    def draw_paper_plane_fallback(self, cx: int, cy: int, width: int, extra_roll: float = 0.0) -> None:
        """Avião de papel desenhado por código, usado se os sprites faltarem (com a cor escolhida)."""
        paint = self.plane_color
        h = width * 0.28
        angle = math.radians(self.roll + extra_roll)
        def rot(px: float, py: float) -> Tuple[int, int]:
            return (int(cx + px * math.cos(angle) - py * math.sin(angle)),
                    int(cy + px * math.sin(angle) + py * math.cos(angle)))
        left_wing = [rot(0, -h * 0.35), rot(-width / 2, h * 0.25), rot(0, h * 0.1)]
        right_wing = [rot(0, -h * 0.35), rot(width / 2, h * 0.25), rot(0, h * 0.1)]
        keel = [rot(0, -h * 0.35), rot(-width * 0.05, h * 0.6), rot(width * 0.05, h * 0.6)]
        light = paint or rgb("ffffff")
        pygame.draw.polygon(self.screen, lerp_color(light, (0, 0, 0), 0.08), left_wing)
        pygame.draw.polygon(self.screen, light, right_wing)
        pygame.draw.polygon(self.screen, lerp_color(light, (40, 50, 60), 0.3), keel)
        pygame.draw.lines(self.screen, rgb("78909c"), True, left_wing + right_wing[1:], 1)

    def draw_player(self) -> None:
        shadow_alpha = int(clamp(150 - self.player_y * 0.5, 40, 150))
        self.draw_ground_shadow(self.player_x, self.player_y, PLAYER_Z, PLANE_WIDTH * (1.1 - self.player_y / 800), shadow_alpha)
        if self.invulnerable_timer > 0 and int(self.elapsed * 14) % 2:
            return
        bob = math.sin(self.elapsed * 3.0) * 3.0
        sx, sy, scale = self.project(self.player_x, self.player_y + bob, PLAYER_Z)
        width = max(8, int(PLANE_WIDTH * scale))
        pose = self.maneuver_pose()
        if pose is not None:
            # Manobra (só visual): desloca, gira, achata/inverte e afasta o desenho.
            m_roll, m_pitch, m_dx, m_dy, m_dz = pose
            style = MANEUVER_STYLES[self.maneuver]
            sx += m_dx * style.sway * width
            sy = max(MANEUVER_TOP_MARGIN, sy - m_dy * style.lift * width)   # não sai pelo alto da tela
            depth = 1.0 / max(0.4, 1.0 + style.depth * m_dz)
        sprite = self.plane_surface()
        if sprite is not None and pose is not None:
            aspect = sprite.get_height() / max(1, sprite.get_width())
            height = max(4, int(width * aspect))
            max_h = int(120 * scale)
            if height > max_h:
                height = max_h
                width = max(8, int(height / aspect))
            vertical = math.cos(math.radians(m_pitch))
            thickness = round(max(MANEUVER_MIN_THICKNESS, abs(vertical)) * 25) / 25
            size = (max(8, int(width * depth)), max(3, int(height * depth * thickness)))
            img = self.scaled_sprite(sprite, ("plane", self.plane_look), size)
            if vertical < 0:               # de cabeça para baixo (topo do looping)
                img = pygame.transform.flip(img, False, True)
            rotated = pygame.transform.rotozoom(img, self.roll + m_roll, 1.0)
            self.screen.blit(rotated, rotated.get_rect(center=(int(sx), int(sy))))
            width = size[0]
        elif sprite is not None:
            aspect = sprite.get_height() / max(1, sprite.get_width())
            height = max(4, int(width * aspect))
            # Pilotos altos aumentam o sprite; limita a altura para não cobrir a tela.
            max_h = int(120 * scale)
            if height > max_h:
                height = max_h
                width = max(8, int(height / aspect))
            base = self.scaled_sprite(sprite, ("plane", self.plane_look), (width, height))
            angle = round(self.roll / 2.0) * 2.0
            cache_key = ("plane_rot", self.plane_look, width, height, angle)
            rotated = self.flipped_sprite_cache.get(cache_key)
            if rotated is None:
                if len(self.flipped_sprite_cache) > 400:
                    self.flipped_sprite_cache.clear()
                rotated = pygame.transform.rotozoom(base, angle, 1.0)
                self.flipped_sprite_cache[cache_key] = rotated
            self.screen.blit(rotated, rotated.get_rect(center=(int(sx), int(sy))))
        else:
            self.draw_paper_plane_fallback(int(sx), int(sy), width, pose[0] if pose else 0.0)
        if self.shield_timer > 0:
            pygame.draw.ellipse(
                self.screen, rgb("40c4ff"),
                pygame.Rect(int(sx - width * 0.62), int(sy - width * 0.36), int(width * 1.24), int(width * 0.72)),
                max(1, int(3 * scale)),
            )
        if self.show_hitboxes:
            pygame.draw.rect(self.screen, rgb("40c4ff"), self.hitbox_screen_rect(self.get_player_hitbox()), 2)

    def draw_floating_texts(self) -> None:
        for text in self.floating:
            x, y, _ = self.project(text.x, text.y, PLAYER_Z)
            surface = self.font.render(text.text, True, rgb("fff59d"))
            surface.set_alpha(int(255 * min(1.0, text.ttl / 0.25)))
            self.screen.blit(surface, surface.get_rect(center=(int(x), int(y))))

    def draw_hud(self) -> None:
        stage = self.current_stage()
        panel = pygame.Surface((570, 104), pygame.SRCALPHA)
        pygame.draw.rect(panel, (12, 24, 18, 225), (0, 0, 558, 92), border_radius=6)
        pygame.draw.rect(panel, stage.accent, (0, 0, 558, 92), 2, border_radius=6)
        self.screen.blit(panel, (0, 0))
        self.screen.blit(self.font.render(f"RESTAURAÇÃO: {math.floor(self.restoration)}%", True, (255, 255, 255)), (18, 12))
        self.screen.blit(self.font.render(f"LIXO: {self.trash_cleaned:,}", True, rgb("ffe0b2")), (300, 12))
        pygame.draw.rect(self.screen, rgb("263238"), (18, 38, 510, 12))
        pygame.draw.rect(self.screen, stage.accent, (18, 38, int(510 * self.restoration / 100), 12))
        self.screen.blit(self.small_font.render(stage.name, True, rgb("c5e1c7")), (18, 57))
        self.screen.blit(
            self.small_font.render(f"RECORDE: {self.high_score:,}   COMBO x{self.combo}", True, rgb("fff59d")),
            (18, 76),
        )

        status = pygame.Surface((292, 88), pygame.SRCALPHA)
        pygame.draw.rect(status, (12, 24, 18, 225), (0, 0, 280, 76), border_radius=6)
        pygame.draw.rect(status, stage.accent, (0, 0, 280, 76), 2, border_radius=6)
        self.screen.blit(status, (790, 12))
        self.screen.blit(self.font.render(f"VIDAS: {self.lives}/3", True, rgb("fff8e1")), (806, 20))
        altitude = f"ALT {int(self.player_y)}"
        self.screen.blit(self.small_font.render(altitude, True, rgb("b3e5fc")), (1000, 26))
        shield = f"ESCUDO {math.ceil(self.shield_timer)}s" if self.shield_timer > 0 else "ESCUDO --"
        magnet = f"IMÃ {math.ceil(self.magnet_timer)}s" if self.magnet_timer > 0 else "IMÃ --"
        self.screen.blit(self.small_font.render(f"{shield}   {magnet}", True, rgb("b3e5fc")), (806, 47))
        self.screen.blit(self.small_font.render("F3: hitboxes | P/ESC: pausa", True, rgb("c5e1c7")), (806, 68))

    def draw_far_layer(self, base: Color) -> None:
        """Camada distante: silhueta do horizonte que desliza devagar (paralaxe)."""
        offset = (-self.cam_x * FAR_SHIFT_PX - self.distance_travelled * FAR_DRIFT_PX) % FAR_TILE
        color = lerp_color(base, rgb("000000"), 0.35)
        n = len(FAR_PROFILE)
        left, right = -FAR_STEP * 2, WIDTH + FAR_STEP * 3
        points = []
        for sx in range(left, right, FAR_STEP):
            idx = int(((sx - offset) % FAR_TILE) // FAR_STEP) % n
            points.append((sx, HORIZON_Y - FAR_PROFILE[idx]))
        points.append((right, HORIZON_Y))
        points.append((left, HORIZON_Y))
        pygame.draw.polygon(self.screen, color, points)

    def draw_background(self) -> None:
        a, b, t = self.visual_stage_pair()
        top = lerp_color(a.sky_top, b.sky_top, t)
        horizon = lerp_color(a.sky_horizon, b.sky_horizon, t)
        self.update_atmosphere(horizon)
        self.screen.blit(self.sky_gradient(top, horizon), (0, 0))
        self.draw_sky_panorama()
        self.draw_clouds()
        self.draw_skyline(horizon)
        # Chão até o horizonte na cor da neblina: emenda suave com o fim da pista.
        pygame.draw.rect(self.screen, self.fog_color, (0, HORIZON_Y, WIDTH, HEIGHT - HORIZON_Y))
        self.draw_world()

    def draw_menu(self) -> None:
        """Hangar: escolha do avião de papel e do piloto (customização)."""
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((5, 10, 9, 190))
        self.screen.blit(overlay, (0, 0))
        accent = self.current_stage().accent
        title = self.title_font.render("HANGAR — escolha seu avião de papel", True, accent)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 52)))

        card = pygame.Rect(WIDTH // 2 - 300, 92, 600, 360)
        pygame.draw.rect(self.screen, (18, 30, 26), card, border_radius=14)
        pygame.draw.rect(self.screen, accent, card, 2, border_radius=14)
        sprite = self.plane_surface(menu=True)
        if sprite is not None:
            box = card.inflate(-60, -60)
            ratio = min(box.width / sprite.get_width(), box.height / sprite.get_height())
            size = (max(1, int(sprite.get_width() * ratio)), max(1, int(sprite.get_height() * ratio)))
            scaled = self.scaled_sprite(sprite, ("menu", self.plane_look), size)
            bob = math.sin(pygame.time.get_ticks() / 400.0) * 6
            self.screen.blit(scaled, scaled.get_rect(center=(card.centerx, int(card.centery + bob))))
        else:
            self.draw_paper_plane_fallback(card.centerx, card.centery, 360)

        arrow = self.title_font.render("◀", True, accent), self.title_font.render("▶", True, accent)
        self.screen.blit(arrow[0], arrow[0].get_rect(center=(card.left - 34, card.centery)))
        self.screen.blit(arrow[1], arrow[1].get_rect(center=(card.right + 34, card.centery)))

        plane_label = self.font.render(f"Avião: {PLANE_MODELS[self.plane_index][1]}", True, (255, 255, 255))
        pilot_label = self.font.render(f"Piloto: {PILOTS[self.pilot_index][1]}", True, rgb("fff59d"))
        self.screen.blit(plane_label, plane_label.get_rect(center=(WIDTH // 2, 478)))
        self.screen.blit(pilot_label, pilot_label.get_rect(center=(WIDTH // 2, 506)))
        status = self.small_font.render(self.webcam_hangar_status(), True, rgb("fff59d"))
        self.screen.blit(status, status.get_rect(center=(WIDTH // 2, 532)))
        if self.control_mode == "mao":
            hints = [
                "Mão para os lados: trocar avião     Mão para cima: trocar piloto",
                "Mão levantada: decolar     Mão para baixo: oficina de pintura",
                f"R: recalibrar     V: trocar o controle     Recorde: {self.high_score:,}",
            ]
        elif self.control_mode == "camera":
            hints = [
                "Corpo ← / →: trocar avião     Corpo ↑ / ↓: trocar piloto",
                "Mão direita levantada: decolar     Mão esquerda levantada: oficina de pintura",
                f"R: recalibrar     V: trocar o controle     Recorde: {self.high_score:,}",
            ]
        else:
            hints = [
                "← / → ou A / D: trocar avião     ↑ / ↓ ou W / S: trocar piloto",
                f"C: oficina de pintura ({self.paint_label()})     V: controle por câmera (corpo ou uma mão)",
                f"ENTER ou ESPAÇO: decolar          Recorde: {self.high_score:,}",
            ]
        for i, line in enumerate(hints):
            surf = self.small_font.render(line, True, rgb("c5e1c7"))
            self.screen.blit(surf, surf.get_rect(center=(WIDTH // 2, 556 + i * 22)))
        if self.uses_camera and self.webcam is not None and self.webcam_surface is not None:
            self.screen.blit(self.webcam_surface, self.webcam_surface.get_rect(topright=(WIDTH - 24, 96)))
            pygame.draw.rect(self.screen, rgb("c5e1c7"),
                             self.webcam_surface.get_rect(topright=(WIDTH - 24, 96)), 1)

    def pattern_thumb(self, pattern: str, size: Tuple[int, int]) -> Optional[pygame.Surface]:
        key = (pattern, size)
        thumb = self.pattern_thumbs.get(key)
        if thumb is None:
            texture = self.pattern_textures.get(pattern)
            if texture is None:
                return None
            thumb = pygame.transform.smoothscale(texture, size)
            self.pattern_thumbs[key] = thumb
        return thumb

    def draw_paint_menu(self) -> None:
        """Oficina de pintura: cor do papel (linha 1) ou padrão do estúdio (linha 2), com prévia ao vivo."""
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((5, 10, 9, 205))
        self.screen.blit(overlay, (0, 0))
        accent = self.current_stage().accent
        title = self.title_font.render("OFICINA DE PINTURA", True, accent)
        self.screen.blit(title, title.get_rect(center=(WIDTH // 2, 34)))
        name = self.font.render(PLANE_MODELS[self.plane_index][1], True, (255, 255, 255))
        self.screen.blit(name, name.get_rect(center=(WIDTH // 2, 68)))

        bob = math.sin(pygame.time.get_ticks() / 400.0) * 5
        cards = (
            (pygame.Rect(60, 88, 600, 292), True, "Hangar (3/4)"),
            (pygame.Rect(690, 88, 350, 292), False, "Em voo"),
        )
        for card, menu_view, label in cards:
            pygame.draw.rect(self.screen, (18, 30, 26), card, border_radius=14)
            pygame.draw.rect(self.screen, accent, card, 2, border_radius=14)
            tag = self.small_font.render(label, True, rgb("c5e1c7"))
            self.screen.blit(tag, (card.x + 14, card.y + 10))
            sprite = self.plane_surface(menu=menu_view)
            box = card.inflate(-60, -70).move(0, 10)
            if sprite is not None:
                ratio = min(box.width / sprite.get_width(), box.height / sprite.get_height())
                size = (max(1, int(sprite.get_width() * ratio)), max(1, int(sprite.get_height() * ratio)))
                scaled = self.scaled_sprite(sprite, ("paint", menu_view, self.plane_look), size)
                self.screen.blit(scaled, scaled.get_rect(center=(box.centerx, int(box.centery + bob))))
            else:
                self.draw_paper_plane_fallback(box.centerx, box.centery, int(box.width * 0.7))

        swatch_w, swatch_h, gap = 52, 40, 8
        pattern_on = self.plane_pattern_key != "liso"

        def row_label(text: str, y: int, active: bool) -> None:
            color = accent if active else rgb("8fa89a")
            surf = self.small_font.render(("▶ " if active else "") + text, True, color)
            self.screen.blit(surf, surf.get_rect(center=(WIDTH // 2, y)))

        def swatch_rects(count: int, y: int):
            total = count * swatch_w + (count - 1) * gap
            x0 = (WIDTH - total) // 2
            return [pygame.Rect(x0 + i * (swatch_w + gap), y, swatch_w, swatch_h) for i in range(count)]

        # Linha 1: cores lisas. Com um padrão escolhido, ela fica apagada.
        row_label("COR" + ("  (o padrão usa as cores próprias; escolher uma cor volta ao liso)" if pattern_on else ""),
                  398, self.paint_row == 0)
        for i, ((_, _, color), rect) in enumerate(zip(PLANE_COLORS, swatch_rects(len(PLANE_COLORS), 410))):
            selected = i == self.paint_index and not pattern_on
            if selected:
                rect = rect.inflate(8, 8)
            if color is None:   # "original": metade papel, metade azul do estúdio
                pygame.draw.rect(self.screen, (245, 245, 240), rect, border_radius=8)
                pygame.draw.polygon(self.screen, rgb("3b82f6"), [rect.topright, rect.bottomright, rect.bottomleft])
            else:
                pygame.draw.rect(self.screen, color, rect, border_radius=8)
            if pattern_on:
                shade = pygame.Surface(rect.size, pygame.SRCALPHA)
                shade.fill((5, 10, 9, 150))
                self.screen.blit(shade, rect)
            outline = accent if selected and self.paint_row == 0 else ((200, 210, 205) if selected else (70, 80, 78))
            pygame.draw.rect(self.screen, outline, rect, 3 if selected else 1, border_radius=8)

        # Linha 2: padrões do estúdio (miniatura da textura).
        row_label("PADRÃO", 474, self.paint_row == 1)
        for i, ((key, _), rect) in enumerate(zip(PLANE_PATTERNS, swatch_rects(len(PLANE_PATTERNS), 486))):
            selected = i == self.pattern_index if pattern_on else key == "liso"
            if selected:
                rect = rect.inflate(8, 8)
            thumb = self.pattern_thumb(key, rect.size) if key != "liso" else None
            if thumb is not None:
                self.screen.blit(thumb, rect)
            else:
                pygame.draw.rect(self.screen, (245, 245, 240) if key == "liso" else (60, 66, 64), rect, border_radius=8)
                text = self.small_font.render("Liso" if key == "liso" else "?", True, (40, 46, 44))
                self.screen.blit(text, text.get_rect(center=rect.center))
            outline = accent if selected and self.paint_row == 1 else ((200, 210, 205) if selected else (70, 80, 78))
            pygame.draw.rect(self.screen, outline, rect, 3 if selected else 1, border_radius=8)

        if pattern_on:
            chosen_text = f"Padrão: {PLANE_PATTERNS[PLANE_PATTERN_KEYS.index(self.plane_pattern_key)][1]}"
        else:
            chosen_text = f"Cor: {PLANE_COLORS[self.paint_index][1]}"
        chosen = self.font.render(chosen_text, True, rgb("fff59d"))
        self.screen.blit(chosen, chosen.get_rect(center=(WIDTH // 2, 552)))
        hints = [
            "↑ / ↓ ou W / S: linha de cores ou de padrões     ← / → ou A / D: escolher (prévia na hora)",
            "ENTER, ESPAÇO ou C: confirmar     ESC: cancelar     A pintura vale só para o papel deste avião.",
        ]
        if self.control_mode == "mao":
            hints.append("Mão para os lados: escolher     para cima: trocar linha     levantada: salvar     para baixo: cancelar")
        elif self.control_mode == "camera":
            hints.append("Corpo ← / → e ↑ / ↓: escolher     Mão direita: salvar     Mão esquerda: cancelar")
        for i, line in enumerate(hints):
            surf = self.small_font.render(line, True, rgb("c5e1c7"))
            self.screen.blit(surf, surf.get_rect(center=(WIDTH // 2, 584 + i * 24)))

    def draw(self) -> None:
        self.draw_background()
        if self.state in ("menu", "paint"):
            if self.state == "menu":
                self.draw_menu()
            else:
                self.draw_paint_menu()
            self.draw_cheat_flash()
            pygame.display.flip()
            return
        self.draw_entities(in_front=False)
        self.draw_player()
        self.draw_entities(in_front=True)
        self.draw_floating_texts()
        self.draw_hud()
        self.draw_webcam_overlay()
        if self.hit_flash_timer > 0:
            flash = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            alpha = int(125 * self.hit_flash_timer / 0.28)
            flash.fill((160, 20, 12, alpha))
            self.screen.blit(flash, (0, 0))
        if self.paused:
            self.draw_overlay("PAUSADO", "O voo está pausado",
                              "P ou ESC: continuar   |   C: voltar ao hangar")
        elif self.game_over:
            self.draw_overlay(
                "FIM DE JOGO",
                f"Resíduos coletados: {self.trash_cleaned:,}   Recorde: {self.high_score:,}",
                "ENTER ou ESPAÇO: voar de novo   |   C: trocar avião no hangar"
                + {"mao": "   |   Mão levantada: voar de novo   Mão para baixo: hangar",
                   "camera": "   |   Mão direita: voar de novo   Mão esquerda: hangar"}.get(self.control_mode, ""),
            )
        self.draw_cheat_flash()
        pygame.display.flip()

    def draw_cheat_flash(self) -> None:
        """Brilho rápido, sem texto, quando o código secreto liga ou desliga."""
        if self.cheat_flash <= 0:
            return
        glow = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        glow.fill((255, 236, 150, int(90 * self.cheat_flash / CHEAT_FLASH_TIME)))
        self.screen.blit(glow, (0, 0))

    def draw_overlay(self, title: str, subtitle: str, hint: str = "") -> None:
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((5, 10, 9, 205))
        self.screen.blit(overlay, (0, 0))
        title_surface = self.title_font.render(title, True, self.current_stage().accent)
        self.screen.blit(title_surface, title_surface.get_rect(center=(WIDTH // 2, HEIGHT // 2 - 36)))
        subtitle_surface = self.font.render(subtitle, True, (255, 255, 255))
        self.screen.blit(subtitle_surface, subtitle_surface.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 8)))
        if hint:
            hint_surface = self.small_font.render(hint, True, rgb("c5e1c7"))
            self.screen.blit(hint_surface, hint_surface.get_rect(center=(WIDTH // 2, HEIGHT // 2 + 48)))

    def run(self, max_frames: Optional[int] = None) -> None:
        """Laço principal. max_frames só é usado pelo --self-test."""
        frames = 0
        try:
            while self.running:
                raw_dt = min(self.clock.tick(FPS) / 1000.0, MAX_DT)
                # Passo de tempo suavizado: o relógio oscila 1–2 ms entre quadros,
                # o que fazia o cenário tremer levemente mesmo a 60 FPS.
                self.smooth_dt += (raw_dt - self.smooth_dt) * DT_SMOOTHING
                dt = self.smooth_dt
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    elif event.type == pygame.KEYDOWN:
                        self.handle_key(event.key)
                    elif event.type == pygame.KEYUP:
                        self.handle_key_up(event.key)
                    elif event.type == getattr(pygame, "WINDOWFOCUSLOST", -1):
                        self.clear_input()  # evita tecla "presa" ao trocar de janela
                self.update(dt)
                self.draw()
                # Usa a folga do quadro para preparar sprites (mais tempo no hangar).
                self.step_warm_up(8.0 if self.state == "menu" else 2.0)
                frames += 1
                if max_frames is not None and frames >= max_frames:
                    self.running = False
        finally:
            # Salva recorde e avião escolhido mesmo se a janela for fechada ou houver erro.
            self.stop_webcam()
            self.save_high_score()
            self.save_selection()
            pygame.quit()


# -----------------------------------------------------------------------------
# PONTO DE ENTRADA
# -----------------------------------------------------------------------------

def _arg_value(argv: List[str], flag: str) -> Optional[str]:
    if flag in argv:
        index = argv.index(flag)
        if index + 1 < len(argv) and not argv[index + 1].startswith("--"):
            return argv[index + 1]
    return None


def run_self_test(frames: int) -> int:
    """Passa pelo hangar e voa N quadros com comandos simulados; grava relatório."""
    game = Game()
    report = {
        "frozen": is_frozen(),
        "app_dir": str(app_dir()),
        "bundle_dir": str(bundle_dir()),
        "data_dir": str(user_data_dir()),
        "save_file": str(save_file_path()),
        "dieselpunk_sprites": sorted(game.side_prop_sprites),
        "powerup_sprites": sorted(game.powerup_sprites),
        "solarpunk_sprites": len(game.tree_sprites),
        "trash_sprites": len(game.trash_sprites),
        "plane_sprites": len(game.plane_sprites),
        "plane_menu_sprites": len(game.plane_menu_sprites),
        "scenario_sprites": len(game.scenario_sprites),
        "skyline_sprites": len(game.skyline_sprites),
        "atmosphere": {"sky_panorama": game.sky_panorama is not None, "clouds": len(game.clouds)},
        "window_size": list(game.screen.get_size()),
        "fps_limit": FPS,
        "high_score": game.high_score,
        "pygame": pygame.version.ver,
        "sdl": ".".join(map(str, pygame.get_sdl_version())),
    }
    game.draw()                       # desenha o hangar uma vez
    game.handle_key(pygame.K_c)       # abre a oficina de pintura,
    game.handle_key(pygame.K_RIGHT)   # testa uma cor
    game.draw()
    game.handle_key(pygame.K_DOWN)    # linha dos padrões
    game.handle_key(pygame.K_RIGHT)   # testa um padrão
    game.draw()
    patterned = game.plane_surface() is not game.plane_sprites.get(game.plane_combo)
    game.handle_key(pygame.K_ESCAPE)  # e cancela (não altera a pintura salva do jogador)
    report["paint_shop"] = {"colors": len(PLANE_COLORS), "patterns": len(game.pattern_textures),
                            "pattern_applied": patterned, "back_to": game.state,
                            "paint_layers": len(game.plane_paint), "menu_paint_layers": len(game.plane_menu_paint),
                            "uv_maps": len(game.plane_uv), "menu_uv_maps": len(game.plane_menu_uv)}
    game.start_run()
    # Cada manobra desenhada em algumas fases (só visual).
    for name, style in MANEUVER_STYLES.items():
        for frac in (0.25, 0.5, 0.75):
            game.start_maneuver(name)
            game.maneuver_time = style.duration * frac
            game.draw()
    report["maneuvers"] = {name: len(rows) for name, rows in game.maneuver_curves.items()}
    game.start_maneuver(START_MANEUVER)
    # Comandos simulados nas 4 direções (um de cada vez), injetados por quadro.
    pattern = [pygame.K_UP, pygame.K_RIGHT, pygame.K_DOWN, pygame.K_LEFT]
    step = max(1, frames // (len(pattern) + 1))
    visited = {"x_min": 0.0, "x_max": 0.0, "y_min": game.player_y, "y_max": game.player_y}
    original_update = game.update

    def scripted_update(dt: float, _frame=[0]) -> None:
        index = _frame[0] // step
        if _frame[0] % step == 0:
            for key in pattern:
                game.handle_key_up(key)
            if index < len(pattern):
                game.handle_key(pattern[index])
        _frame[0] += 1
        game.invulnerable_timer = max(game.invulnerable_timer, 0.5)  # o teste não deve terminar em game over
        original_update(dt)
        visited["x_min"] = min(visited["x_min"], game.player_x)
        visited["x_max"] = max(visited["x_max"], game.player_x)
        visited["y_min"] = min(visited["y_min"], game.player_y)
        visited["y_max"] = max(visited["y_max"], game.player_y)

    game.update = scripted_update  # type: ignore[method-assign]
    game.run(max_frames=frames)
    report["flight_range"] = {k: round(v, 1) for k, v in visited.items()}
    report["frames"] = frames
    report["status"] = "ok"
    report_path = user_data_dir() / "self_test.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if sys.stdout is not None:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def log_crash() -> Optional[Path]:
    try:
        log_path = user_data_dir() / "eco_runner_erro.log"
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        return log_path
    except OSError:
        return None


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if "--generate-3d" in argv:
            output = _arg_value(argv, "--output-dir")
            obj_path, mtl_path = export_solarpunk_tree_obj(
                TREE_OBJ_FILENAME, Path(output) if output else None
            )
            if is_frozen() and sys.stdout is None:
                show_message(
                    "Eco Runner — Modelo 3D",
                    f"Modelo gerado:\n{obj_path}\n{mtl_path}",
                )
            return 0
        if "--self-test" in argv:
            value = _arg_value(argv, "--self-test")
            return run_self_test(int(value) if value and value.isdigit() else 180)
        Game().run()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception:
        log_path = log_crash()
        where = f"\nDetalhes técnicos em:\n{log_path}" if log_path else ""
        show_message(
            "Eco Runner",
            "O jogo encontrou um erro e precisou ser fechado." + where,
        )
        return 1
    finally:
        if pygame.get_init():
            pygame.quit()


if __name__ == "__main__":
    sys.exit(main())
