"""Configuração compartilhada da suíte do Eco Runner (headless, sem janela/áudio)."""

import os
import sys
from pathlib import Path

# Deve vir antes de qualquer uso do pygame/SDL.
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import pygame  # noqa: E402
import pytest  # noqa: E402

import eco_runner  # noqa: E402


@pytest.fixture
def game(monkeypatch):
    """Jogo no hangar, com o sorteio de obstáculos desligado.

    Os testes inserem as Entity à mão (game.entities) na altura desejada.
    """
    instance = eco_runner.Game()
    monkeypatch.setattr(instance, "spawn_pattern", lambda z: None)
    instance.entities.clear()
    yield instance


@pytest.fixture(autouse=True)
def modo_dificil_por_padrao(monkeypatch):
    """A suíte antiga descreve o jogo original, que hoje é o modo Difícil.

    Para o jogador sem configuração salva o padrão é o Normal; os testes do Normal
    trocam o modo explicitamente (tests/test_modos.py).
    """
    monkeypatch.setattr(eco_runner, "DEFAULT_GAME_MODE", "dificil")


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Isola recorde/relatórios em tmp_path e impede leitura do save legado do projeto."""
    data_dir = tmp_path / "dados"
    monkeypatch.setenv("ECO_RUNNER_DATA_DIR", str(data_dir))
    monkeypatch.setattr(eco_runner, "_DATA_DIR_CACHE", None)
    monkeypatch.setattr(
        eco_runner,
        "legacy_save_paths",
        lambda: [tmp_path / "legado" / eco_runner.SAVE_FILENAME],
    )
    yield data_dir
    eco_runner._DATA_DIR_CACHE = None
    if pygame.get_init():
        pygame.quit()
