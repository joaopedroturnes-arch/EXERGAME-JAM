"""Suíte pytest headless do Eco Runner (avião de papel, hangar e voo).

Sem janela nem áudio: SDL usa drivers 'dummy' (ver conftest.py). Nos testes de
voo, o sorteio de obstáculos fica desligado pela fixture `game` e cada teste
insere as Entity na altura desejada, com dt fixo de 1/60 s.

Testes marcados com xfail(strict=True) documentam comportamentos conhecidos
ainda não alterados no jogo. Se forem corrigidos, o xfail vira falha e deve
ser removido.
"""

from __future__ import annotations

import json
import math
import py_compile
import random
from pathlib import Path

import pygame
import pytest

import eco_runner
from eco_runner import (
    CONFIG_FILENAME,
    FPS,
    HEIGHT,
    LANE_WIDTH,
    MAX_ALTITUDE,
    MAX_PLAYER_X,
    MAX_ROLL_DEG,
    MIN_ALTITUDE,
    OBSTACLE_KINDS,
    OBSTACLE_SPECS,
    PILOTS,
    PLANE_MODELS,
    PLAYER_Z,
    STAGES,
    TRASH_HEIGHTS,
    TRASH_MODELS,
    TREE_OBJ_FILENAME,
    WIDTH,
    Entity,
    Game,
    Hitbox,
)

DT = 1.0 / 60.0
PROJECT_DIR = Path(eco_runner.__file__).resolve().parent
SRC = PROJECT_DIR / "eco_runner.py"
N_PLANES = len(PLANE_MODELS)
N_PILOTS = len(PILOTS)


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


def add(game: Game, kind: str, lane: int = 0, y: float = 0.0,
        z: float = PLAYER_Z, sprite: str | None = None) -> Entity:
    if sprite is None:
        if kind in OBSTACLE_KINDS:
            sprite = OBSTACLE_SPECS[kind][0].sprite
        elif kind == "trash":
            sprite = TRASH_MODELS[0]
        else:
            sprite = ""
    entity = Entity(z, lane, kind, y, sprite)
    game.entities.append(entity)
    return entity


def collect_one(game: Game) -> None:
    game.collect_trash(Entity(PLAYER_Z, 0, "trash", 60.0, TRASH_MODELS[0]))


def take_three_hits(game: Game) -> None:
    for _ in range(3):
        game.invulnerable_timer = 0.0
        game.take_hit()


def read_obj(obj_path: Path) -> dict:
    """Lê um .obj e devolve contagens e referências usadas (para validar)."""
    data = {"v": [], "vt": [], "vn": [], "faces": [], "usemtl": [], "mtllib": [], "groups": []}
    for raw in obj_path.read_text(encoding="utf-8").splitlines():
        parts = raw.split()
        if not parts or parts[0] == "#":
            continue
        tag, args = parts[0], parts[1:]
        if tag == "v":
            data["v"].append(tuple(float(a) for a in args))
        elif tag == "vt":
            data["vt"].append(tuple(float(a) for a in args))
        elif tag == "vn":
            data["vn"].append(tuple(float(a) for a in args))
        elif tag == "f":
            data["faces"].append([[int(i) for i in tok.split("/") if i] for tok in args])
        elif tag == "usemtl":
            data["usemtl"].append(args[0])
        elif tag == "mtllib":
            data["mtllib"].append(args[0])
        elif tag == "g":
            data["groups"].append(args[0])
    return data


# ------------------------------------------------------------ script e janela
def test_script_compila(tmp_path):
    # cfile em pasta temporária: não grava __pycache__ dentro do projeto.
    py_compile.compile(str(SRC), cfile=str(tmp_path / "eco_runner.pyc"), doraise=True)


def test_janela_1100x650_e_fps_60(game):
    assert (WIDTH, HEIGHT) == (1100, 650)
    assert FPS == 60
    assert game.screen.get_size() == (1100, 650)


def test_run_chama_clock_tick_com_fps_60(game):
    ticks = []

    class FakeClock:
        def tick(self, fps):
            ticks.append(fps)
            return 16

    game.clock = FakeClock()
    game.run(max_frames=3)
    assert ticks == [60, 60, 60]


def test_quit_encerra_run_sem_systemexit_e_salva_recorde(isolated_data_dir):
    game = Game()
    game.trash_cleaned = 420          # sem passar por collect_trash: força o recorde
    pygame.event.post(pygame.event.Event(pygame.QUIT))
    game.run()                        # não pode lançar SystemExit
    assert game.running is False
    assert not pygame.get_init()
    saved = json.loads(eco_runner.save_file_path().read_text(encoding="utf-8"))
    assert saved["recorde"] == 420


# ------------------------------------------------------------------- hangar
def test_jogo_comeca_no_hangar(game):
    assert game.state == "menu"
    assert game.paused is False and game.game_over is False


def test_update_nao_avanca_no_hangar(game):
    before = (game.elapsed, game.distance_travelled, list(game.segments), len(game.entities))
    advance(game, 2.0)
    after = (game.elapsed, game.distance_travelled, list(game.segments), len(game.entities))
    assert before == after
    assert game.state == "menu"


def test_hangar_desenha_sem_erro(game):
    game.draw()
    assert game.screen.get_size() == (WIDTH, HEIGHT)


@pytest.mark.parametrize("key, start, expected", [
    (pygame.K_LEFT, 0, N_PLANES - 1),
    (pygame.K_a, 0, N_PLANES - 1),
    (pygame.K_RIGHT, N_PLANES - 1, 0),
    (pygame.K_d, N_PLANES - 1, 0),
    (pygame.K_RIGHT, 4, 5),
])
def test_hangar_troca_aviao_com_wrap_around(game, key, start, expected):
    game.plane_index = start
    game.handle_key(key)
    assert game.plane_index == expected
    assert game.state == "menu"


@pytest.mark.parametrize("key, start, expected", [
    (pygame.K_UP, 0, N_PILOTS - 1),
    (pygame.K_w, 0, N_PILOTS - 1),
    (pygame.K_DOWN, N_PILOTS - 1, 0),
    (pygame.K_s, N_PILOTS - 1, 0),
    (pygame.K_DOWN, 2, 3),
])
def test_hangar_troca_piloto_com_wrap_around(game, key, start, expected):
    game.pilot_index = start
    game.handle_key(key)
    assert game.pilot_index == expected
    assert game.state == "menu"


@pytest.mark.parametrize("key", [pygame.K_RETURN, pygame.K_SPACE])
def test_enter_e_espaco_decolam(game, key):
    game.handle_key(key)
    assert game.state == "playing"
    assert game.held == set()
    assert game.lives == 3


def test_setas_nao_iniciam_voo(game):
    for key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
        game.handle_key(key)
    assert game.state == "menu"


# -------------------------------------------------------- seleção e recorde
def test_selecao_persiste_entre_instancias(isolated_data_dir):
    first = Game()
    first.plane_index = 3
    first.pilot_index = 5
    first.handle_key(pygame.K_RETURN)          # decolar grava a escolha
    config = json.loads((eco_runner.user_data_dir() / CONFIG_FILENAME).read_text(encoding="utf-8"))
    assert config == {"aviao": PLANE_MODELS[3][0], "piloto": PILOTS[5][0], "cores": {}, "padroes": {},
                      "controle": "teclado"}
    second = Game()
    assert (second.plane_index, second.pilot_index) == (3, 5)


@pytest.mark.parametrize("conteudo", [
    "{quebrado",
    '{"aviao": "nao_existe", "piloto": "x"}',
    "[]",
    "",
])
def test_config_invalida_usa_padrao(isolated_data_dir, conteudo):
    (eco_runner.user_data_dir() / CONFIG_FILENAME).write_text(conteudo, encoding="utf-8")
    game = Game()
    assert (game.plane_index, game.pilot_index) == (0, 1)


def test_plane_combo_sem_piloto_usa_sprite_sem_piloto(game):
    game.pilot_index = 0
    assert game.plane_combo == f"{PLANE_MODELS[game.plane_index][0]}__none"
    assert game.plane_surface() is game.plane_sprites[game.plane_combo]


def test_recorde_salvo_e_carregado(isolated_data_dir):
    game = Game()
    game.trash_cleaned = 300
    game.save_high_score()
    assert Game().high_score == 300


@pytest.mark.parametrize("conteudo", [
    "{corrompido",
    '{"recorde": "abc"}',
    '{"recorde": -5}',
    "[]",
    "",
])
def test_recorde_corrompido_vira_zero(isolated_data_dir, conteudo):
    eco_runner.save_file_path().write_text(conteudo, encoding="utf-8")
    assert Game().high_score == 0


# ---------------------------------------------------------------------- voo
@pytest.mark.parametrize("key, attr, sign", [
    (pygame.K_RIGHT, "player_x", 1),
    (pygame.K_d, "player_x", 1),
    (pygame.K_LEFT, "player_x", -1),
    (pygame.K_a, "player_x", -1),
    (pygame.K_UP, "player_y", 1),
    (pygame.K_w, "player_y", 1),
    (pygame.K_SPACE, "player_y", 1),
    (pygame.K_DOWN, "player_y", -1),
    (pygame.K_s, "player_y", -1),
])
def test_segurar_tecla_move_no_sentido_certo(game, key, attr, sign):
    start_flight(game)
    before = getattr(game, attr)
    game.handle_key(key)
    advance(game, 0.2)
    delta = getattr(game, attr) - before
    assert delta * sign > 0, f"{attr} deveria mudar no sentido {sign}, mudou {delta}"


def test_soltar_tecla_para_o_aviao(game):
    start_flight(game)
    game.handle_key(pygame.K_RIGHT)
    advance(game, 0.3)
    game.handle_key_up(pygame.K_RIGHT)
    assert game.held == set()
    advance(game, 1.0)                        # a inércia se dissipa
    assert abs(game.player_vx) < 1.0
    x_parado = game.player_x
    advance(game, 0.5)
    assert abs(game.player_x - x_parado) < 1.0


def test_teclas_de_voo_entram_em_held(game):
    start_flight(game)
    game.handle_key(pygame.K_UP)
    assert game.held == {"up"}
    game.handle_key(pygame.K_a)
    assert game.held == {"up", "left"}
    game.handle_key_up(pygame.K_UP)
    assert game.held == {"left"}


@pytest.mark.parametrize("key, attr, expected", [
    (pygame.K_RIGHT, "player_x", MAX_PLAYER_X),
    (pygame.K_LEFT, "player_x", -MAX_PLAYER_X),
    (pygame.K_UP, "player_y", MAX_ALTITUDE),
    (pygame.K_DOWN, "player_y", MIN_ALTITUDE),
])
def test_limites_de_voo_sao_respeitados_em_todo_quadro(game, key, attr, expected):
    start_flight(game)
    game.handle_key(key)
    for _ in range(5 * 60):
        game.update(DT)
        assert MIN_ALTITUDE - 1e-9 <= game.player_y <= MAX_ALTITUDE + 1e-9
        assert abs(game.player_x) <= MAX_PLAYER_X + 1e-9
    assert getattr(game, attr) == pytest.approx(expected)


def test_roll_inclina_ao_ir_para_o_lado(game):
    start_flight(game)
    game.handle_key(pygame.K_RIGHT)
    advance(game, 0.3)
    assert game.roll < -5, "indo para a direita o nariz deve inclinar para a direita (roll negativo)"
    game.handle_key_up(pygame.K_RIGHT)
    advance(game, 2.0)
    assert abs(game.roll) < 0.5
    game.handle_key(pygame.K_LEFT)
    advance(game, 0.3)
    assert game.roll > 5
    assert abs(game.roll) <= MAX_ROLL_DEG + 1e-9


def test_soltar_uma_de_duas_teclas_iguais_nao_para_o_aviao(game):
    start_flight(game)
    game.handle_key(pygame.K_UP)
    game.handle_key(pygame.K_w)
    game.handle_key_up(pygame.K_UP)           # W continua pressionada
    assert "up" in game.held


# --------------------------------------------------------- pausa e game over
@pytest.mark.parametrize("pause_key", [pygame.K_p, pygame.K_ESCAPE])
def test_pausa_congela_voo_e_limpa_teclas(game, pause_key):
    start_flight(game)
    game.handle_key(pygame.K_RIGHT)
    advance(game, 0.2)
    game.handle_key(pause_key)
    assert game.paused is True
    assert game.held == set()
    snapshot = (game.player_x, game.player_y, game.elapsed, game.distance_travelled)
    game.handle_key(pygame.K_RIGHT)           # tecla durante a pausa é ignorada
    advance(game, 1.0)
    assert (game.player_x, game.player_y, game.elapsed, game.distance_travelled) == snapshot
    assert game.held == set()
    game.handle_key(pause_key)
    assert game.paused is False


@pytest.mark.parametrize("key", [pygame.K_c, pygame.K_TAB])
def test_c_e_tab_na_pausa_voltam_ao_hangar(game, key):
    start_flight(game)
    game.handle_key(pygame.K_p)
    game.handle_key(key)
    assert game.state == "menu"
    assert game.paused is False


@pytest.mark.parametrize("key", [pygame.K_c, pygame.K_TAB])
def test_c_e_tab_no_game_over_voltam_ao_hangar(game, key):
    start_flight(game)
    take_three_hits(game)
    assert game.game_over
    game.handle_key(key)
    assert game.state == "menu"


@pytest.mark.parametrize("key", [pygame.K_RETURN, pygame.K_SPACE])
def test_reinicio_apos_game_over_com_enter_ou_espaco(game, key):
    start_flight(game)
    game.trash_cleaned = 50
    take_three_hits(game)
    game.handle_key(key)
    assert game.state == "playing"
    assert game.game_over is False
    assert game.lives == 3
    assert game.trash_cleaned == 0


def test_f3_alterna_hitboxes_e_draw_funciona(game):
    start_flight(game)
    add(game, "trash", lane=-1, y=32.0, z=PLAYER_Z + 100)
    add(game, "low", lane=0, z=PLAYER_Z + 200)
    add(game, "gate", lane=1, z=PLAYER_Z + 300)
    add(game, "tower", lane=-1, z=PLAYER_Z - 20)
    add(game, "shield", lane=0, y=60.0, z=PLAYER_Z + 50)
    game.handle_key(pygame.K_F3)
    assert game.show_hitboxes is True
    game.draw()
    game.handle_key(pygame.K_F3)
    assert game.show_hitboxes is False
    game.draw()


def test_draw_com_overlays_de_pausa_e_game_over(game):
    start_flight(game)
    game.handle_key(pygame.K_p)
    game.draw()
    game.handle_key(pygame.K_p)
    take_three_hits(game)
    game.draw()


# ------------------------------------------------------------------ colisões
def test_hitbox_intersecta_so_quando_sobrepoe_nos_tres_eixos():
    base = Hitbox(0, 10, 0, 10, 0, 10)
    assert base.intersects(Hitbox(5, 15, 5, 15, 5, 15))
    assert not base.intersects(Hitbox(11, 20, 0, 10, 0, 10))   # x
    assert not base.intersects(Hitbox(0, 10, 11, 20, 0, 10))   # y
    assert not base.intersects(Hitbox(0, 10, 0, 10, 11, 20))   # z


def test_hitbox_do_aviao_fica_na_profundidade_do_jogador(game):
    box = game.get_player_hitbox()
    assert box.z_min == pytest.approx(PLAYER_Z - 27.0)
    assert box.z_max == pytest.approx(PLAYER_Z + 27.0)


def test_entity_x_e_lane_vezes_largura():
    assert Entity(PLAYER_Z, -1, "trash").x == -LANE_WIDTH
    assert Entity(PLAYER_Z, 1, "low").x == LANE_WIDTH


@pytest.mark.parametrize("altitude, colide", [
    (60.0, True), (100.0, True), (112.0, True), (118.0, False), (140.0, False),
])
def test_low_colide_so_voando_baixo(game, altitude, colide):
    """low (tambores): y_max=100; o avião (meia altura 17) colide até y=117."""
    start_flight(game)
    game.player_y = altitude
    add(game, "low", lane=0)
    game.update(DT)
    assert (game.lives == 2) is colide


@pytest.mark.parametrize("altitude, colide", [
    (60.0, False), (80.0, False), (120.0, True), (160.0, True),
])
def test_gate_colide_alto_e_nao_colide_baixo(game, altitude, colide):
    """gate (tubos_valvula): y_min=105; passar por baixo é seguro."""
    start_flight(game)
    game.player_y = altitude
    add(game, "gate", lane=0)
    game.update(DT)
    assert (game.lives == 2) is colide


@pytest.mark.parametrize("sprite", ["chamine", "caldeira"])
@pytest.mark.parametrize("altitude", [MIN_ALTITUDE, 60.0, 120.0, MAX_ALTITUDE])
def test_tower_colide_na_mesma_faixa_em_qualquer_altura(game, sprite, altitude):
    start_flight(game)
    game.player_y = altitude
    game.player_x = 0.0
    add(game, "tower", lane=0, sprite=sprite)
    game.update(DT)
    assert game.lives == 2


@pytest.mark.parametrize("sprite", ["chamine", "caldeira"])
def test_tower_nao_colide_desviando_para_o_lado(game, sprite):
    start_flight(game)
    game.player_x = LANE_WIDTH                 # faixa vizinha
    add(game, "tower", lane=0, sprite=sprite)
    game.update(DT)
    assert game.lives == 3


def test_lixo_coletado_na_mesma_altura(game):
    start_flight(game)
    game.player_y = TRASH_HEIGHTS[0]
    trash = add(game, "trash", lane=0, y=TRASH_HEIGHTS[0])
    game.update(DT)
    assert trash.collected is True
    assert game.trash_cleaned == 15


def test_lixo_nao_coletado_em_altura_diferente(game):
    start_flight(game)
    game.player_y = TRASH_HEIGHTS[0]
    trash = add(game, "trash", lane=0, y=TRASH_HEIGHTS[2])
    game.update(DT)
    assert trash.collected is False
    assert game.trash_cleaned == 0


def test_ima_coleta_lixo_proximo_sem_encostar(game):
    start_flight(game)
    game.player_y = 60.0
    # Faixa vizinha (220 unidades): sem sobreposição direta com o avião.
    near = add(game, "trash", lane=1, y=60.0)
    game.update(DT)
    assert near.collected is False            # controle: sem ímã não coleta

    game.magnet_timer = 7.0
    near = add(game, "trash", lane=1, y=60.0)
    game.update(DT)
    assert near.collected is True


@pytest.mark.parametrize("lane, z, y", [
    (1, PLAYER_Z + 100.0, 60.0),   # longe na profundidade
    (1, PLAYER_Z, 148.0),          # longe na altura
])
def test_ima_nao_coleta_lixo_distante(game, lane, z, y):
    start_flight(game)
    game.player_y = MIN_ALTITUDE              # a 148 o alcance vertical (110) fica de fora
    game.magnet_timer = 7.0
    far = add(game, "trash", lane=lane, y=y, z=z)
    game.update(DT)
    assert far.collected is False


def test_escudo_bloqueia_colisao(game):
    start_flight(game)
    game.shield_timer = 6.0
    add(game, "low", lane=0)
    game.update(DT)
    assert game.lives == 3
    assert game.game_over is False
    assert game.invulnerable_timer == 0.0


@pytest.mark.parametrize("kind, attr, duracao", [("shield", "shield_timer", 6.0),
                                                 ("magnet", "magnet_timer", 7.0)])
def test_powerup_ativa_duracao(game, kind, attr, duracao):
    start_flight(game)
    game.player_y = 60.0
    item = add(game, kind, lane=0, y=60.0)
    game.update(DT)
    assert item.collected is True
    assert getattr(game, attr) == pytest.approx(duracao)


def test_invulnerabilidade_apos_colisao(game):
    start_flight(game)
    game.take_hit()
    assert game.lives == 2
    assert game.invulnerable_timer == pytest.approx(1.25)
    game.take_hit()                            # ainda invulnerável
    assert game.lives == 2
    game.invulnerable_timer = 0.0
    game.take_hit()
    assert game.lives == 1


def test_colisao_continua_com_mesmo_obstaculo_conta_uma_vez(game):
    start_flight(game)
    game.player_y = 60.0
    add(game, "low", lane=0)
    for _ in range(18):                        # 0.3 s: o obstáculo atravessa o avião
        game.update(DT)
    assert game.lives == 2


def test_game_over_apos_tres_colisoes(game):
    start_flight(game)
    for expected in (2, 1):
        game.invulnerable_timer = 0.0
        game.take_hit()
        assert game.lives == expected
        assert game.game_over is False
    game.invulnerable_timer = 0.0
    game.take_hit()
    assert game.lives == 0
    assert game.game_over is True
    assert game.state == "playing"


def test_reparo_recupera_vida_ou_restauracao(game):
    start_flight(game)
    game.lives = 2
    game.player_y = 60.0
    add(game, "repair", lane=0, y=60.0)
    game.update(DT)
    assert game.lives == 3
    add(game, "repair", lane=0, y=60.0)       # já com 3 vidas: vira restauração
    game.update(DT)
    assert game.lives == 3
    assert game.restoration == pytest.approx(5.0 + 3.0)


def test_entidades_passadas_sao_removidas(game):
    start_flight(game)
    passed = add(game, "trash", lane=0, y=TRASH_HEIGHTS[2], z=PLAYER_Z - 71.0)
    behind_limit = add(game, "trash", lane=0, y=TRASH_HEIGHTS[2], z=PLAYER_Z - 60.0)
    game.update(DT)
    assert passed not in game.entities
    assert behind_limit in game.entities


# ----------------------------------------------------------- combo e pontuação
def test_combo_sobe_a_cada_quatro_coletas(game):
    start_flight(game)
    for _ in range(4):
        collect_one(game)
    assert game.combo == 2
    assert game.streak == 4
    assert game.trash_cleaned == 60            # 4 x 15 com combo x1


def test_colisao_zera_combo(game):
    start_flight(game)
    for _ in range(4):
        collect_one(game)
    game.take_hit()
    assert game.combo == 1
    assert game.streak == 0


@pytest.mark.xfail(strict=True, reason=(
    "BUG: update_combo() so zera streak quando combo > 1 (linha 825). Com combo=1 e streak=3, "
    "o tempo expira mas o streak continua; a proxima coleta chega a 4 e sobe o combo para x2"))
def test_combo_quebra_quando_o_tempo_expira(game):
    start_flight(game)
    for _ in range(3):
        collect_one(game)
    advance(game, 2.5)                         # combo_timer (2.2 s) expira
    collect_one(game)
    assert game.combo == 1


# ------------------------------------------------------- obstáculos e lixo
def test_colisao_com_obstaculo_nao_congela_entidades_seguintes(game):
    start_flight(game)
    game.player_y = 60.0
    game.shield_timer = 6.0                    # colisão bloqueada, mas o laço ainda quebra
    add(game, "low", lane=0)
    trash = add(game, "trash", lane=0, y=60.0)
    z_antes = trash.z
    game.update(DT)
    assert trash.z == pytest.approx(z_antes - game.speed * DT)


def test_ordem_fixa_dos_modelos_de_lixo(game):
    random.seed(7)
    game.entities.clear()
    game.trash_counter = 0
    # O fixture desliga spawn_pattern na instância; chama-se o método original da classe.
    for i in range(12):
        Game.spawn_pattern(game, 500.0 + i * 100.0)
    sprites = [e.sprite for e in game.entities if e.kind == "trash"]
    assert len(sprites) >= 12
    assert sprites == [TRASH_MODELS[i % len(TRASH_MODELS)] for i in range(len(sprites))]


def test_run_novo_reinicia_ordem_de_lixo_no_primeiro_modelo(isolated_data_dir):
    random.seed(3)
    game = Game()
    game.start_run()
    sprites = [e.sprite for e in game.entities if e.kind == "trash"]
    assert len(sprites) >= 10
    assert sprites[:10] == TRASH_MODELS


@pytest.mark.parametrize("kind", OBSTACLE_KINDS)
def test_ordem_fixa_dos_modelos_de_obstaculos(game, kind):
    options = [spec.sprite for spec in OBSTACLE_SPECS[kind]]
    game.obstacle_counters = {k: 0 for k in OBSTACLE_KINDS}
    sequence = [game.next_obstacle(kind) for _ in range(len(options) * 2 + 1)]
    assert sequence == [options[i % len(options)] for i in range(len(sequence))]


def test_contadores_de_obstaculos_sao_independentes(game):
    game.obstacle_counters = {k: 0 for k in OBSTACLE_KINDS}
    assert game.next_obstacle("gate") == "tubos_valvula"
    assert game.next_obstacle("tower") == OBSTACLE_SPECS["tower"][0].sprite
    assert game.next_obstacle("tower") == OBSTACLE_SPECS["tower"][1].sprite


# ------------------------------------------------------------------- eras
def test_quatro_eras_por_restauracao(game):
    assert len(STAGES) == 4
    expected = {0: "DIESELPUNK", 24.9: "DIESELPUNK", 25: "CYBER_POLLUTION",
                50: "ECO_TRANSITION", 75: "SOLARPUNK_NOUVEAU", 100: "SOLARPUNK_NOUVEAU"}
    for value, stage_id in expected.items():
        game.restoration = float(value)
        assert game.current_stage().stage_id == stage_id, value


def test_visual_stage_pair_interpola_entre_eras(game):
    game.restoration = 37.5
    a, b, t = game.visual_stage_pair()
    assert (a.stage_id, b.stage_id) == ("CYBER_POLLUTION", "ECO_TRANSITION")
    assert t == pytest.approx(0.5)


# ----------------------------------------------------------------- sprites
def test_sprites_presentes_sao_carregados_de_assets(game):
    assert eco_runner.find_asset_dir("plane_sprites").resolve() == (PROJECT_DIR / "assets" / "plane_sprites").resolve()
    assert len(game.plane_sprites) == 77
    assert len(game.plane_menu_sprites) == 77
    assert set(game.plane_sprites) == {f"{m}__{p}" for m, _ in PLANE_MODELS for p, _ in PILOTS}
    assert len(game.tree_sprites) == 10
    assert len(game.trash_sprites) == 10
    assert len(game.side_prop_sprites) == 8
    assert len(game.powerup_sprites) == 3
    # Camadas de pintura: uma por combinação, do mesmo tamanho do sprite original.
    assert len(game.plane_paint) == 77 and len(game.plane_menu_paint) == 77
    for combo, layer in game.plane_paint.items():
        assert layer.get_size() == game.plane_sprites[combo].get_size(), combo
    for combo, layer in game.plane_menu_paint.items():
        assert layer.get_size() == game.plane_menu_sprites[combo].get_size(), combo


def test_sem_sprites_usa_desenhos_de_reserva(tmp_path, monkeypatch):
    ausente = tmp_path / "sem_assets"          # pasta que não existe
    monkeypatch.setattr(eco_runner, "asset_dir_candidates", lambda name: [ausente / name])
    game = Game()
    assert game.plane_sprites == {}
    assert game.trash_sprites == {}
    assert game.tree_sprites == {}
    assert game.side_prop_sprites == {}
    assert game.powerup_sprites == {}
    assert game.plane_surface() is None

    game.draw()                                # hangar com avião de reserva
    game.handle_key(pygame.K_c)                # oficina de pintura sem sprites
    game.handle_key(pygame.K_RIGHT)
    game.draw()
    game.handle_key(pygame.K_RETURN)
    game.start_run()
    game.entities.clear()
    add(game, "trash", lane=-1, y=32.0, z=PLAYER_Z + 100)
    add(game, "low", lane=0, z=PLAYER_Z + 200)
    add(game, "gate", lane=1, z=PLAYER_Z + 300)
    add(game, "tower", lane=-1, z=PLAYER_Z - 20)
    add(game, "shield", lane=0, y=60.0, z=PLAYER_Z + 50)
    game.show_hitboxes = True
    for restoration in (0.0, 30.0, 60.0, 90.0):
        game.restoration = restoration
        game.draw()
        advance(game, 0.1)
        game.draw()


# ----------------------------------------------------- 3D, self-test e main
def test_generate_3d_com_pasta_com_espaco_gera_obj_e_mtl_validos(tmp_path):
    out = tmp_path / "pasta com espaço"
    rc = eco_runner.main(["--generate-3d", "--output-dir", str(out)])
    assert rc == 0
    obj_path = out / TREE_OBJ_FILENAME
    mtl_path = obj_path.with_suffix(".mtl")
    assert obj_path.is_file() and mtl_path.is_file()

    data = read_obj(obj_path)
    assert data["mtllib"] == [mtl_path.name]
    assert all(all(math.isfinite(c) for c in v) for v in data["v"])
    assert len(data["groups"]) == 6 + 1        # 6 seções do tronco + copa
    assert "Solar_Canopy" in data["groups"]

    # Todas as referências de faces precisam existir nas listas.
    for face in data["faces"]:
        for ref in face:
            vi = ref[0]
            assert 1 <= vi <= len(data["v"])
            if len(ref) > 1:
                assert 1 <= ref[1] <= len(data["vt"])
            if len(ref) > 2:
                assert 1 <= ref[2] <= len(data["vn"])
    assert len(data["faces"]) == 2 * 16 * 6 + 6  # tronco (2 triângulos por quad) + 6 da copa

    mtl_names = {line.split()[1] for line in mtl_path.read_text(encoding="utf-8").splitlines()
                 if line.startswith("newmtl ")}
    assert set(data["usemtl"]) <= mtl_names


def test_self_test_retorna_zero_e_grava_relatorio(isolated_data_dir):
    rc = eco_runner.main(["--self-test", "30"])
    assert rc == 0
    report = json.loads((eco_runner.user_data_dir() / "self_test.json").read_text(encoding="utf-8"))
    assert report["status"] == "ok"
    assert report["frames"] == 30
    assert report["plane_sprites"] == 77


def test_main_sem_argumentos_cria_jogo_e_roda(monkeypatch):
    chamadas = []
    monkeypatch.setattr(Game, "run", lambda self, max_frames=None: chamadas.append(max_frames))
    assert eco_runner.main([]) == 0
    assert chamadas == [None]


def test_main_com_erro_grava_log_e_retorna_1(monkeypatch, isolated_data_dir):
    mensagens = []

    def falha(self, max_frames=None):
        raise RuntimeError("falha de teste")

    monkeypatch.setattr(Game, "run", falha)
    monkeypatch.setattr(eco_runner, "show_message", lambda title, text: mensagens.append(text))
    assert eco_runner.main([]) == 1
    log = (eco_runner.user_data_dir() / "eco_runner_erro.log").read_text(encoding="utf-8")
    assert "falha de teste" in log
    assert mensagens


# ------------------------------------------- cenário em camadas e fluidez
def test_trecho_da_pista_mantem_cor_e_cenario_ao_ser_reciclado(game):
    """Regressão: a cor das faixas e o objeto das margens dependiam da posição
    na lista de trechos. Cada vez que o primeiro trecho era reciclado (~5x por
    segundo) tudo trocava de paridade: faixas piscavam e prédios pulavam."""
    start_flight(game)
    ids = {}
    recycled = 0
    for _ in range(240):
        base_before = game.segment_base
        game.update(DT)
        recycled += game.segment_base - base_before
        for i, z in enumerate(game.segments):
            absolute = round(z + game.distance_travelled)
            seg = game.segment_base + i
            assert ids.setdefault(absolute, seg) == seg
    assert recycled >= 10


def test_modelos_do_kit_dieselpunk_scenario_sao_carregados(game):
    assert len(game.scenario_sprites) == len(eco_runner.SCENARIO_SPRITES) == 28
    assert len(game.skyline_sprites) == len(eco_runner.SKYLINE_SPRITES)
    assert game.sky_panorama is not None
    assert len(game.clouds) > 0
    for name, _ in eco_runner.MARGIN_PROP_SPECS + eco_runner.MID_ROW_SPECS:
        assert game.scenery_sprite(name) is not None, name


def test_neblina_esconde_o_fim_da_pista_e_nao_afeta_o_que_esta_perto(game):
    assert game.fog_level(PLAYER_Z) == 0
    assert game.fog_level(eco_runner.FOG_START) == 0
    assert game.fog_level(eco_runner.FOG_END + 10) == eco_runner.FOG_LEVELS
    levels = [game.fog_level(z) for z in range(0, 2600, 50)]
    assert levels == sorted(levels)


def test_cenario_desenha_em_todas_as_eras_e_com_camera_deslocada(game):
    start_flight(game)
    while game.warm_up_queue is not None:
        game.step_warm_up(50)
    for restoration in (0.0, 30.0, 55.0, 90.0):
        game.restoration = restoration
        for cam in (-77.0, 0.0, 77.0):
            game.cam_x = cam
            game.draw()
            advance(game, 0.05)


def test_spec_empacota_todas_as_pastas_de_assets():
    spec = (PROJECT_DIR / "EcoRunner.spec").read_text(encoding="utf-8")
    for folder in (PROJECT_DIR / "assets").iterdir():
        if folder.is_dir():
            assert f'"{folder.name}"' in spec, folder.name


def is_concrete(color) -> bool:
    """Cinza/marrom acinzentado: canais próximos, sem predominância de verde ou azul."""
    return max(color.r, color.g, color.b) - min(color.r, color.g, color.b) < 45 and color.b <= color.r + 5


def test_chao_de_concreto_na_fase_inicial_e_grama_onde_as_arvores_aparecem(game):
    start_flight(game)
    assert game.grass_texture is not None and game.concrete_texture is not None
    blue = pygame.Color(0, 0, 255, 255)
    row = 300                                                      # linha com chão dos dois lados da pista
    sides = [x for x in range(0, WIDTH, 7) if x < 300 or x > WIDTH - 300]

    game.restoration = 5.0                                         # fase inicial: só concreto
    game.screen.fill(blue)
    game.draw_ground(1000.0)
    assert all(is_concrete(game.screen.get_at((x, row))) for x in (5, 150, WIDTH - 150, WIDTH - 5))
    assert game.screen.get_at((WIDTH // 2, row)) == blue           # o meio fica para a pista
    before = [tuple(game.screen.get_at((x, row))) for x in sides]
    game.distance_travelled += eco_runner.CONCRETE_TILE_Z * 0.37   # a pista andou: o chão desliza
    game.draw_ground(1000.0)
    assert before != [tuple(game.screen.get_at((x, row))) for x in sides]

    game.restoration = 60.0                                        # árvores: grama até a frente
    wave_z = 180.0 + (game.restoration / 100.0) ** 1.15 * 2150.0
    y_start = int(eco_runner.HORIZON_Y + eco_runner.CAMERA_HEIGHT * eco_runner.FOV / wave_z)
    game.screen.fill(blue)
    game.draw_ground(wave_z)
    assert is_concrete(game.screen.get_at((5, y_start - 4)))       # além da frente: concreto
    grass = game.screen.get_at((5, y_start + 40))
    assert grass.g > grass.b and grass.g > grass.r                 # aquém: grama


def test_sem_textura_de_grama_o_concreto_nao_cobre_a_area_restaurada(game, monkeypatch):
    start_flight(game)
    game.ground_textures.pop("grass")
    game.grass_texture = None
    game.restoration = 60.0
    game.draw()                                                    # não pode falhar
    wave_z = 180.0 + (game.restoration / 100.0) ** 1.15 * 2150.0
    blue = pygame.Color(0, 0, 255, 255)
    game.screen.fill(blue)
    game.draw_ground(wave_z)
    assert game.screen.get_at((5, 300)) == blue                    # fica a grama de reserva do polígono


# ------------------------------------------------------- oficina de pintura
def test_oficina_de_pintura_previa_cancelar_confirmar_e_salvar(isolated_data_dir):
    game = Game()
    assert game.state == "menu" and game.plane_color_key == "original"
    game.handle_key(pygame.K_c)
    assert game.state == "paint"
    game.handle_key(pygame.K_RIGHT)                       # prévia na hora
    assert game.plane_color_key == eco_runner.PLANE_COLOR_KEYS[1]
    game.handle_key(pygame.K_ESCAPE)                      # cancela: volta a cor anterior
    assert game.state == "menu" and game.plane_color_key == "original"

    game.handle_key(pygame.K_c)
    game.handle_key(pygame.K_LEFT)                        # dá a volta na paleta
    assert game.plane_color_key == eco_runner.PLANE_COLOR_KEYS[-1]
    game.handle_key(pygame.K_RIGHT)
    game.handle_key(pygame.K_RIGHT)
    game.handle_key(pygame.K_RIGHT)
    game.handle_key(pygame.K_RETURN)                      # confirma e grava
    chosen = eco_runner.PLANE_COLOR_KEYS[2]
    assert game.state == "menu" and game.plane_color_key == chosen
    config = json.loads((eco_runner.user_data_dir() / CONFIG_FILENAME).read_text(encoding="utf-8"))
    assert config["cores"] == {game.plane_key: chosen}

    painted_plane = game.plane_key
    game.handle_key(pygame.K_RIGHT)                       # outro avião: cor própria (original)
    assert game.plane_color_key == "original"
    again = Game()                                        # reabrir o jogo mantém a cor
    assert again.plane_colors == {painted_plane: chosen}


def test_config_com_cor_invalida_e_ignorada(isolated_data_dir):
    path = eco_runner.user_data_dir() / CONFIG_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"aviao": "dart", "piloto": "zen",
                                "cores": {"dart": "nao_existe", "glider": "azul", "xyz": "azul"}}), encoding="utf-8")
    game = Game()
    assert game.plane_colors == {"glider": "azul"}
    assert game.plane_color_key == "original"             # dart com cor inválida: original


def test_cor_pinta_so_o_papel_e_mantem_o_piloto(game):
    game.plane_index = 0
    game.pilot_index = 1                                  # com piloto
    combo = game.plane_combo
    base = game.plane_sprites[combo]
    paint = game.plane_paint[combo]
    game.plane_colors[game.plane_key] = "vermelho"
    painted = game.plane_surface()
    assert painted.get_size() == base.get_size()
    w, h = base.get_size()
    paper = pilot = 0
    for x in range(0, w, 3):
        for y in range(0, h, 3):
            p = paint.get_at((x, y))
            b = base.get_at((x, y))
            c = painted.get_at((x, y))
            if p.a == 255:                                # papel visível: fica vermelho
                assert c.r > c.g + 60 and c.r > c.b + 60, (x, y, c)
                paper += 1
            elif p.a == 0 and b.a == 255:                 # piloto e outras peças: intactos
                assert tuple(c) == tuple(b), (x, y)
                pilot += 1
    assert paper > 200 and pilot > 5
    game.plane_colors[game.plane_key] = "original"        # original: sprite do estúdio sem tinta
    assert game.plane_surface() is base


# ------------------------------------------------- padrões de pintura (Oficina)
def test_mapas_uv_e_texturas_dos_padroes_estao_presentes(game):
    assert len(game.plane_uv) == 77 and len(game.plane_menu_uv) == 77
    for combo, uv in game.plane_uv.items():
        assert uv.get_size() == game.plane_sprites[combo].get_size(), combo
    for combo, uv in game.plane_menu_uv.items():
        assert uv.get_size() == game.plane_menu_sprites[combo].get_size(), combo
    assert set(game.pattern_textures) == set(eco_runner.PLANE_PATTERN_KEYS[1:])
    for texture in game.pattern_textures.values():
        assert texture.get_size() == (256, 256)


def test_oficina_linha_de_padroes_previa_cancelar_e_salvar(isolated_data_dir):
    game = Game()
    keys = eco_runner.PLANE_PATTERN_KEYS
    game.handle_key(pygame.K_c)
    assert game.paint_row == 0
    game.handle_key(pygame.K_DOWN)                        # vai para a linha dos padrões
    assert game.paint_row == 1
    game.handle_key(pygame.K_RIGHT)                       # prévia na hora
    assert game.plane_pattern_key == keys[1]
    assert game.plane_color_key == "original"             # a cor não muda nessa linha
    game.draw()
    game.handle_key(pygame.K_ESCAPE)                      # cancela
    assert game.state == "menu" and game.plane_pattern_key == "liso"

    game.handle_key(pygame.K_c)
    game.handle_key(pygame.K_s)
    game.handle_key(pygame.K_LEFT)                        # dá a volta: último padrão
    assert game.plane_pattern_key == keys[-1]
    game.handle_key(pygame.K_RETURN)
    config = json.loads((eco_runner.user_data_dir() / CONFIG_FILENAME).read_text(encoding="utf-8"))
    assert config["padroes"] == {game.plane_key: keys[-1]}
    assert Game().plane_pattern_key == keys[-1]           # reabrir o jogo mantém o padrão

    game.handle_key(pygame.K_c)                           # com padrão, a oficina abre na linha 2
    assert game.paint_row == 1
    game.handle_key(pygame.K_UP)
    game.handle_key(pygame.K_RIGHT)                       # escolher uma cor volta ao liso
    assert game.plane_pattern_key == "liso"
    assert game.plane_color_key == eco_runner.PLANE_COLOR_KEYS[1]


def test_config_com_padrao_invalido_e_ignorado(isolated_data_dir):
    path = eco_runner.user_data_dir() / CONFIG_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"aviao": "dart", "piloto": "zen",
                                "padroes": {"dart": "nao_existe", "glider": "xadrez", "xyz": "xadrez"}}),
                    encoding="utf-8")
    game = Game()
    assert game.plane_patterns == {"glider": "xadrez"}
    assert game.plane_pattern_key == "liso"


def test_padrao_veste_so_o_papel_e_mantem_o_piloto(game):
    game.plane_index = 0
    game.pilot_index = 1
    combo = game.plane_combo
    base = game.plane_sprites[combo]
    paint = game.plane_paint[combo]
    game.plane_patterns[game.plane_key] = "xadrez"
    painted = game.plane_surface()
    assert painted.get_size() == base.get_size()
    w, h = base.get_size()
    dark = light = pilot = 0
    for x in range(0, w, 2):
        for y in range(0, h, 2):
            p = paint.get_at((x, y))
            b = base.get_at((x, y))
            c = painted.get_at((x, y))
            if p.a == 255:
                lum = (c.r + c.g + c.b) / 3
                dark += lum < 60
                light += lum > 150
            elif p.a == 0 and b.a == 255:
                assert tuple(c) == tuple(b), (x, y)
                pilot += 1
    assert dark > 50 and light > 50 and pilot > 5          # casas pretas e brancas no papel
    game.plane_colors[game.plane_key] = "vermelho"        # com padrão, a cor não é usada
    assert pygame.image.tobytes(game.plane_surface(), "RGBA") == pygame.image.tobytes(painted, "RGBA")


def test_padrao_sem_mapa_uv_usa_a_cor(game):
    game.plane_index = 0
    game.pilot_index = 1
    combo = game.plane_combo
    game.plane_uv.pop(combo)
    game.plane_patterns[game.plane_key] = "galaxia"
    assert game.plane_surface() is game.plane_sprites[combo]       # sem cor: original
    game.plane_colors[game.plane_key] = "vermelho"
    tinted = game.plane_surface()
    game.plane_patterns[game.plane_key] = "liso"
    solid = game.plane_surface()
    assert pygame.image.tobytes(tinted, "RGBA") == pygame.image.tobytes(solid, "RGBA")


# -------------------------------------------------------------------- manobras
def test_manobras_carregadas_do_pacote_3d(game):
    curves = game.maneuver_curves
    assert set(curves) == set(eco_runner.MANEUVER_STYLES)
    for name, rows in curves.items():
        assert rows[0][0] == 0.0 and rows[-1][0] == 1.0, name
        assert all(a[0] < b[0] for a, b in zip(rows, rows[1:])), name
        assert all(abs(v) < 1e-3 for v in rows[-1][3:]), name     # termina no lugar
    assert abs(curves["tonneau"][-1][1]) == pytest.approx(360.0, abs=1.0)
    assert max(r[2] for r in curves["looping"]) == pytest.approx(360.0, abs=1.0)
    assert 60.0 < max(r[2] for r in curves["cobra"]) < 90.0
    data = json.loads((PROJECT_DIR / "assets" / "maneuvers" / "maneuvers.json").read_text(encoding="utf-8"))
    assert data["tonneau"]["source"].endswith(".gltf")


def test_sem_json_de_manobras_usa_curvas_de_reserva(tmp_path, monkeypatch):
    monkeypatch.setattr(eco_runner, "asset_dir_candidates", lambda name: [tmp_path / name])
    curves = eco_runner.load_maneuvers()
    assert set(curves) == set(eco_runner.MANEUVER_STYLES)
    assert curves["tonneau"][-1][1] == pytest.approx(-360.0)


def test_decolar_faz_a_manobra_de_decolagem(game):
    start_flight(game)
    assert game.maneuver == eco_runner.START_MANEUVER
    advance(game, eco_runner.MANEUVER_STYLES[eco_runner.START_MANEUVER].duration + 0.1)
    assert game.maneuver is None and game.maneuver_pose() is None


@pytest.mark.parametrize("kind", ["shield", "magnet", "repair"])
def test_power_up_dispara_manobra_so_visual(game, kind):
    start_flight(game)
    game.maneuver = None
    before = game.get_player_hitbox()
    add(game, kind, lane=0, y=game.player_y)
    game.player_x = 0.0
    game.update(DT)
    expected = eco_runner.POWERUP_MANEUVERS[kind]
    assert game.maneuver == expected
    after = game.get_player_hitbox()
    assert (after.x_min, after.y_min, after.z_min) == pytest.approx((before.x_min, before.y_min, before.z_min), abs=1.0)  # a colisão não se move
    duration = eco_runner.MANEUVER_STYLES[expected].duration
    for frac in (0.25, 0.5, 0.75):
        game.maneuver = expected
        game.maneuver_time = duration * frac
        game.draw()                                       # não pode falhar em nenhuma fase
    game.maneuver_time = 0.0
    advance(game, duration + 0.1)
    assert game.maneuver is None


def test_looping_inverte_e_sobe_o_aviao_no_topo(game):
    start_flight(game)
    game.entities.clear()
    game.maneuver = None
    game.draw()
    normal = game.screen.copy()
    game.start_maneuver("looping")
    game.maneuver_time = eco_runner.MANEUVER_STYLES["looping"].duration * 0.5
    roll, pitch, dx, dy, dz = game.maneuver_pose()
    assert pitch == pytest.approx(180.0, abs=10.0) and dy > 0.9
    game.draw()
    _, sy, _ = game.project(game.player_x, game.player_y, PLAYER_Z)
    # Algo foi desenhado acima da posição normal do avião (o topo do looping).
    rows_changed = [y for y in range(0, int(sy) - 60, 4)
                    if any(game.screen.get_at((x, y)) != normal.get_at((x, y))
                           for x in range(WIDTH // 2 - 120, WIDTH // 2 + 120, 6))]
    assert rows_changed
