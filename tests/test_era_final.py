"""Suíte da era final do Eco Runner (EcoUrbe Solarpunk, restauração >= 66,7%: última das 3 eras).

Cobre: carregamento de sprites e FX, empacotamento, sorteio só depois de 66,7%,
clareza de colisão medida nos próprios sprites, jogabilidade por altitude e faixa,
transição por trechos, desenho sem erro, decoração que não colide e chão/pista.

Como em test_eco_runner.py: headless (conftest.py), dt fixo de 1/60 s e Entity
inseridas à mão quando o teste precisa de uma posição exata.
"""

from __future__ import annotations

import random
from pathlib import Path

import pygame
import pytest

import eco_runner
from eco_runner import (
    FINAL_FX,
    FINAL_OBSTACLE_SPECS,
    FINAL_SKY_DECOR,
    FINAL_SPRITES,
    FINAL_TRAM,
    LANE_WIDTH,
    OBSTACLE_KINDS,
    OBSTACLE_SPECS,
    PLAYER_Z,
    Entity,
    Game,
    is_final_obstacle,
    obstacle_spec,
)

DT = 1.0 / 60.0
PROJECT_DIR = Path(eco_runner.__file__).resolve().parent
FINAL_DIR = PROJECT_DIR / "assets"
ALL_FINAL_SPECS = [(kind, spec) for kind, specs in FINAL_OBSTACLE_SPECS.items() for spec in specs]
ALL_FINAL_IDS = [f"{kind}-{spec.sprite}" for kind, spec in ALL_FINAL_SPECS]
DECOR_NAMES = {name for name, *_ in FINAL_SKY_DECOR} | {FINAL_TRAM[0]}


# ----------------------------------------------------------------- auxiliares
def advance(game: Game, seconds: float) -> None:
    for _ in range(int(round(seconds / DT))):
        game.update(DT)


def start_flight(game: Game) -> Game:
    """Decola pelo hangar (ENTER) e limpa as entidades sorteadas no início."""
    game.handle_key(pygame.K_RETURN)
    assert game.state == "playing"
    game.entities.clear()
    return game


def sprite_surface(name: str, folder: str = "era_final_sprites") -> pygame.Surface:
    return pygame.image.load(str(FINAL_DIR / folder / f"{name}.png"))


def is_clear(surface: pygame.Surface, x: int, y: int) -> bool:
    return surface.get_at((x, y)).a <= 40


def collides(game: Game, entity: Entity, player_x: float, player_y: float) -> bool:
    game.player_x = player_x
    game.player_y = player_y
    return game.get_player_hitbox().intersects(game.get_entity_hitbox(entity))


def final_entity(kind: str, sprite: str, lane: int = 0) -> Entity:
    return Entity(PLAYER_Z, lane, kind, 0.0, sprite)


def spawn_many(game: Game, n: int = 400) -> list:
    """Sorteio real (spawn_pattern) em n colunas; devolve só os obstáculos."""
    game.entities.clear()
    for i in range(n):
        game.spawn_pattern(520.0 + (i % 16) * 120.0)
    return [e for e in game.entities if e.kind in OBSTACLE_KINDS]


@pytest.fixture
def world():
    """Jogo com o sorteio real ligado (sem entrar em partida)."""
    instance = Game()
    instance.entities.clear()
    return instance


@pytest.fixture
def no_spawn(monkeypatch):
    """Jogo em voo sem sorteio de novas entidades."""
    instance = Game()
    monkeypatch.setattr(instance, "spawn_pattern", lambda z: None)
    start_flight(instance)
    instance.cheat_invincible = True
    yield instance


# ------------------------------------------------- 1. carregamento e empacotamento
def test_sprites_e_fx_da_era_final_existem_e_carregam():
    for name in FINAL_SPRITES:
        path = FINAL_DIR / "era_final_sprites" / f"{name}.png"
        assert path.is_file(), path
        assert sprite_surface(name).get_width() > 0
    for name in FINAL_FX:
        path = FINAL_DIR / "era_final_fx" / f"{name}.png"
        assert path.is_file(), path
        assert sprite_surface(name, "era_final_fx").get_width() > 0
    game = Game()
    assert set(game.final_sprites) == set(FINAL_SPRITES)
    assert set(game.final_fx) == set(FINAL_FX)


def test_empacotamento_inclui_as_pastas_da_era_final():
    spec_text = (PROJECT_DIR / "EcoRunner.spec").read_text(encoding="utf-8")
    assert '"era_final_sprites"' in spec_text
    assert '"era_final_fx"' in spec_text


# ----------------------------------------- 2. abaixo de 66,7% nada muda
def test_abaixo_de_75_o_sorteio_fica_na_era_anterior(world):
    world.restoration = 60
    assert world.final_share() == 0.0
    assert world.final_since == {}
    random.seed(20240601)
    zs = [520.0 + (i % 16) * 120.0 for i in range(400)]
    assert not any(world.spawn_is_final(z) for z in zs)
    obstacles = spawn_many(world)
    assert len(obstacles) > 80
    assert not [e for e in world.entities if e.sprite.startswith("EF_")]
    assert not any(is_final_obstacle(e) for e in obstacles)
    world.obstacle_counters = {kind: 0 for kind in OBSTACLE_KINDS}
    for kind in OBSTACLE_KINDS:
        names = [spec.sprite for spec in OBSTACLE_SPECS[kind]]
        assert [world.next_obstacle(kind) for _ in range(2 * len(names))] == names * 2


# ----------------------------------------------- 3. acima de 90% só era final
def test_acima_de_90_so_obstaculos_da_era_final(world):
    counters_before = dict(world.final_counters)
    world.restoration = 90
    assert world.final_share() == 1.0
    random.seed(20240602)
    obstacles = spawn_many(world)
    assert len(obstacles) > 80
    for e in obstacles:
        assert e.sprite in {s.sprite for s in FINAL_OBSTACLE_SPECS[e.kind]}
        assert is_final_obstacle(e)
        assert obstacle_spec(e) in FINAL_OBSTACLE_SPECS[e.kind]
    final_names = {spec.sprite for _, spec in ALL_FINAL_SPECS}
    assert {e.sprite for e in obstacles} == final_names
    # Ordem fixa por tipo: cada tipo percorre o seu ciclo, na ordem de aparição.
    for kind in OBSTACLE_KINDS:
        names = [s.sprite for s in FINAL_OBSTACLE_SPECS[kind]]
        seq = [e.sprite for e in obstacles if e.kind == kind]
        start = counters_before[kind]
        assert seq == [names[(start + i) % len(names)] for i in range(len(seq))]


# ----------------------------------------------- 4. clareza de colisão (sprites)
@pytest.mark.parametrize("kind,spec", ALL_FINAL_SPECS, ids=ALL_FINAL_IDS)
def test_colisao_condiz_com_o_desenho(kind, spec):
    if kind == "low":
        # Voe por cima: o topo da colisão fica abaixo do topo do sprite.
        assert spec.y_max < spec.visual_height
        return
    surface = sprite_surface(spec.sprite)
    w, h = surface.get_size()
    if kind == "gate":
        # Passe por baixo: o vão livre no centro existe até y_min e o vão começa alto.
        assert spec.y_min >= 105
        frac = spec.y_min / spec.visual_height
        cx = w // 2
        cols = range(cx - 3, cx + 4)
        rows = [y for y in range(h) if 1 - (y + 0.5) / h < frac]
        clear = sum(is_clear(surface, x, y) for y in rows for x in cols) / (len(rows) * len(cols))
        assert clear >= 0.9, f"vão no centro só {clear:.0%} transparente abaixo de y_min"
    else:
        # Desvie para o lado: a largura da colisão não passa do tamanho visível (x1,25).
        xs = [x for x in range(w) if not is_clear(surface, x, h // 2)]
        assert xs, "sprite sem pixels visíveis na metade da altura"
        visible = (max(xs) - min(xs) + 1) * spec.visual_height / h
        assert spec.width <= visible * 1.25, (
            f"colisão {spec.width:.0f} > visível {visible:.1f} x1,25 na metade da altura"
        )


# ----------------------------------------------- 5. jogabilidade (altitude e faixa)
def test_low_final_bate_voando_baixo(world):
    for spec in FINAL_OBSTACLE_SPECS["low"]:
        assert collides(world, final_entity("low", spec.sprite), 0.0, 60.0), spec.sprite


def test_gate_final_passa_por_baixo_e_bate_alto(world):
    for spec in FINAL_OBSTACLE_SPECS["gate"]:
        entity = final_entity("gate", spec.sprite)
        assert not collides(world, entity, 0.0, 60.0), spec.sprite
        assert collides(world, entity, 0.0, 140.0), spec.sprite


def test_tower_final_bate_de_frente(world):
    for spec in FINAL_OBSTACLE_SPECS["tower"]:
        assert collides(world, final_entity("tower", spec.sprite), 0.0, 60.0), spec.sprite


@pytest.mark.parametrize("kind,spec", ALL_FINAL_SPECS, ids=ALL_FINAL_IDS)
def test_faixa_vizinha_nao_bate_em_obstaculo_final(world, kind, spec):
    entity = final_entity(kind, spec.sprite, lane=0)
    for player_x in (LANE_WIDTH, -LANE_WIDTH):
        for player_y in (60.0, 140.0):
            assert not collides(world, entity, player_x, player_y), (spec.sprite, player_x, player_y)


# ----------------------------------------------- 6. transição por trechos
def test_transicao_por_trechos_cresce_e_limpa_ao_voltar(no_spawn):
    game = no_spawn
    game.restoration = 90
    assert game.final_share() == 1.0
    antigos = set(game.final_since)
    assert antigos
    novo = None
    valores = []
    for _ in range(int(round(3.0 / DT))):
        game.update(DT)
        if novo is None:
            entrantes = sorted(set(game.final_since) - antigos)
            if entrantes:
                novo = entrantes[0]
        if novo is not None and novo in game.final_since:
            valores.append(game.segment_final(novo))
    assert novo is not None, "nenhum trecho novo chegou em 3 s"
    assert valores[0] < 0.05, valores[:3]
    assert all(b >= a - 1e-12 for a, b in zip(valores, valores[1:]))
    assert valores[-1] >= 0.999
    for seg in game.final_since:
        assert game.segment_base <= seg < game.segment_base + len(game.segments)
    game.restoration = 60
    assert game.final_since == {}
    assert game.final_flags() is None


# ----------------------------------------------- 7. desenho e legenda
@pytest.mark.parametrize("restoration", [60, 95])
@pytest.mark.parametrize("hitboxes", [False, True])
def test_draw_nao_quebra(restoration, hitboxes):
    game = Game()
    game.restoration = restoration
    game.state = "playing"
    game.cheat_invincible = True
    game.show_hitboxes = hitboxes
    random.seed(7)
    advance(game, 1.0)
    game.draw()
    game.draw()
    assert game.state == "playing"


def test_decoracao_anda_e_nao_colide(no_spawn):
    game = no_spawn
    game.restoration = 90
    decor_before = list(game.decor_x)
    tram_before = game.tram_x
    advance(game, 0.5)
    assert game.decor_x != decor_before
    assert game.tram_x != tram_before
    assert not [e for e in game.entities if e.sprite in DECOR_NAMES]


# ----------------------------------------------- 8. chão e pista
def ground_names_used(game: Game, monkeypatch) -> list:
    names: list = []
    original = game.ground_row_info

    def spy(name, group):
        names.append(name)
        return original(name, group)

    monkeypatch.setattr(game, "ground_row_info", spy)
    game.draw_ground()
    return names


def test_chao_e_pista_da_era_final_usam_texturas_novas(monkeypatch):
    game = Game()
    game.restoration = 90
    game.state = "playing"
    names = ground_names_used(game, monkeypatch)
    assert "meadow" in names
    assert "paver_road" in names

    control = Game()
    control.restoration = 60
    control.state = "playing"
    names = ground_names_used(control, monkeypatch)
    assert "meadow" not in names
    assert "paver_road" not in names


def test_sem_textura_de_pista_ou_prado_o_desenho_continua():
    game = Game()
    game.restoration = 90
    game.state = "playing"
    game.ground_textures.pop("paver_road", None)
    game.ground_textures.pop("meadow", None)
    game.draw()
    assert game.state == "playing"
