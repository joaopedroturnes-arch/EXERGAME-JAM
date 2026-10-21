"""Modo Normal (novo, mais calmo) x modo Difícil (o jogo original)."""
from __future__ import annotations

import json
import random

import pygame
import pytest

import eco_runner
from eco_runner import (
    BASE_SPEED,
    CONFIG_FILENAME,
    NORMAL_RESTORATION_PER_TRASH,
    NORMAL_SPEED_FACTOR,
    NORMAL_TRASH_EVERY,
    NORMAL_TRASH_POINTS,
    RESTORATION_PER_TRASH,
    Entity,
    Game,
    user_data_dir,
)

DT = 1.0 / 60.0


def advance(game: Game, seconds: float) -> None:
    for _ in range(int(round(seconds / DT))):
        game.update(DT)


def in_flight(mode: str, spawn: bool = False) -> Game:
    game = Game()
    game.game_mode = mode
    if not spawn:
        game.spawn_pattern = lambda z: None
    game.handle_key(pygame.K_RETURN)
    assert game.state == "playing"
    game.entities.clear()
    game.cheat_invincible = True
    return game


def test_jogador_novo_comeca_no_normal(monkeypatch):
    monkeypatch.setattr(eco_runner, "DEFAULT_GAME_MODE", "normal")
    assert Game().game_mode == "normal"


def test_tecla_m_no_hangar_alterna_e_salva():
    game = Game()
    assert game.state == "menu"
    assert game.game_mode == "dificil"
    game.handle_key(pygame.K_m)
    assert game.game_mode == "normal"
    data = json.loads((user_data_dir() / CONFIG_FILENAME).read_text(encoding="utf-8"))
    assert data["modo"] == "normal"
    assert Game().game_mode == "normal"
    game.handle_key(pygame.K_m)
    assert game.game_mode == "dificil"
    assert Game().game_mode == "dificil"


def test_modo_invalido_na_configuracao_volta_ao_padrao():
    path = user_data_dir() / CONFIG_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"modo": "impossivel"}), encoding="utf-8")
    assert Game().game_mode == eco_runner.DEFAULT_GAME_MODE


def test_normal_voa_na_metade_da_velocidade():
    hard, normal = in_flight("dificil"), in_flight("normal")
    assert normal.speed == pytest.approx(BASE_SPEED * NORMAL_SPEED_FACTOR)
    for game in (hard, normal):
        game.restoration = 50
        advance(game, 1.0)
    assert normal.speed == pytest.approx(hard.speed * NORMAL_SPEED_FACTOR, rel=0.02)
    assert NORMAL_SPEED_FACTOR == 0.5


def count_trash(mode: str, patterns: int = 800) -> int:
    game = Game()
    game.game_mode = mode
    game.reset()
    game.entities.clear()
    random.seed(11)
    for i in range(patterns):
        game.spawn_pattern(1000.0 + i)
    return sum(1 for e in game.entities if e.kind == "trash")


def test_normal_tem_um_quarto_do_lixo():
    hard, normal = count_trash("dificil"), count_trash("normal")
    assert NORMAL_TRASH_EVERY == 4
    assert 0.20 < normal / hard < 0.30


def test_normal_mantem_obstaculos_e_power_ups():
    def others(mode):
        game = Game()
        game.game_mode = mode
        game.reset()
        game.entities.clear()
        random.seed(5)
        for i in range(800):
            game.spawn_pattern(1000.0 + i)
        return sum(1 for e in game.entities if e.kind != "trash")
    hard, normal = others("dificil"), others("normal")
    assert normal > 0.85 * hard


def test_lixo_no_normal_vale_65_pontos_e_restaura_mais():
    game = in_flight("normal")
    game.restoration = 10
    game.wallet = 0
    for i in range(6):
        game.collect_trash(Entity(300.0, 0, "trash", 88.0))
    assert NORMAL_TRASH_POINTS == 65
    assert game.trash_cleaned == 6 * NORMAL_TRASH_POINTS == 390
    assert game.wallet == 390
    assert game.combo == 1                                    # sem combo no Normal
    assert game.restoration == pytest.approx(10 + 6 * NORMAL_RESTORATION_PER_TRASH)
    assert NORMAL_RESTORATION_PER_TRASH == pytest.approx(RESTORATION_PER_TRASH * 4 / 0.5)


def test_dificil_continua_igual():
    game = in_flight("dificil")
    game.restoration = 10
    game.collect_trash(Entity(300.0, 0, "trash", 88.0))
    assert game.trash_cleaned == 15
    assert game.restoration == pytest.approx(10 + RESTORATION_PER_TRASH)


def test_eras_chegam_em_tempo_parecido():
    """Restauração por segundo de voo (pegando todo lixo) fica igual nos dois modos."""
    per_second = {}
    for mode in ("dificil", "normal"):
        trash_per_distance = count_trash(mode) / 800
        speed = BASE_SPEED * (NORMAL_SPEED_FACTOR if mode == "normal" else 1.0)
        per_trash = NORMAL_RESTORATION_PER_TRASH if mode == "normal" else RESTORATION_PER_TRASH
        per_second[mode] = trash_per_distance * speed * per_trash
    assert per_second["normal"] == pytest.approx(per_second["dificil"], rel=0.2)


@pytest.mark.parametrize("mode, halos", [("dificil", 1), ("normal", 0)])
def test_brilho_dos_coletaveis_so_no_dificil(monkeypatch, mode, halos):
    game = in_flight(mode)
    assert game.final_fx.get("halo_coletavel") is not None
    calls = []
    monkeypatch.setattr(game, "final_at", lambda z: True)
    monkeypatch.setattr(game, "blit_world_sprite", lambda *a, **k: calls.append(a))
    game.draw_collectible_halo(Entity(300.0, 0, "trash", 88.0), 46.0)
    game.draw_collectible_halo(Entity(300.0, 1, "shield", 88.0), 56.0)
    assert len(calls) == 2 * halos


def test_recorde_separado_e_carteira_unica():
    game = in_flight("normal")
    game.wallet = 0
    for _ in range(4):
        game.collect_trash(Entity(300.0, 0, "trash", 88.0))
    game.save_high_score()
    again = Game()
    again.game_mode = "normal"
    assert again.high_score == 4 * 65
    again.game_mode = "dificil"
    assert again.high_score == 0
    assert again.wallet == 4 * 65


@pytest.mark.parametrize("mode", ["normal", "dificil"])
def test_desenho_nos_dois_modos(mode):
    game = in_flight(mode, spawn=True)
    game.restoration = 90
    random.seed(3)
    advance(game, 1.0)
    game.draw()
    game.state = "menu"
    game.draw()
