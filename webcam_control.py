"""Controle do jogo pela webcam (MediaPipe Pose), em dois modos.

Adaptado da técnica do T-TEA 2.0 (torre interativa para crianças com TEA):
o MediaPipe Tasks (PoseLandmarker em modo VIDEO) lê a imagem da webcam, espelhada
como num espelho, e encontra os pontos do corpo.

Modo "corpo" (``mode="corpo"``): usa o centro do tronco.
- voo: inclinar para os lados move o avião; levantar o corpo sobe; agachar desce;
- menus: inclinar = setas; mão direita levantada confirma; mão esquerda abre a
  Oficina (hangar) ou cancela.

Modo "uma mão" (``mode="mao"``): usa só o pulso de uma mão (``HAND``).
- voo: a mão é um joystick; mover para os lados, para cima ou para baixo move o avião;
- menus: deixar a mão um instante à esquerda/direita = setas; para cima = próximo
  piloto ou troca de linha; para baixo = Oficina, cancelar ou voltar ao hangar;
  levantada acima do ombro = decolar, salvar ou voar de novo.

Antes de usar, o jogo calibra a posição de repouso (cerca de 2 s parado).
Depois disso, o deslocamento em relação a esse ponto vira um eixo de -1 a 1.

Dependências são opcionais: sem ``mediapipe`` e ``opencv`` o jogo segue só com
o teclado e mostra o motivo no hangar. O módulo não importa essas bibliotecas
ao ser carregado; elas são importadas só quando a câmera é iniciada.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

Center = Tuple[float, float]              # posição normalizada (0..1 na imagem)
Hands = Tuple[bool, bool]                 # (mão esquerda levantada, mão direita levantada)

MODES = ("corpo", "mao")
HAND = "right"                            # mão do modo "uma mão": "right" ou "left"
TORSO_LANDMARKS = (11, 12, 23, 24)       # ombros e quadris (índices do MediaPipe Pose)
SHOULDER = {"left": 11, "right": 12}
WRIST = {"left": 15, "right": 16}
MIN_VISIBILITY = 0.5
RAISE_MARGIN = 0.03                       # pulso pelo menos 3% da altura da imagem acima do ombro
PREVIEW_SIZE = (160, 120)                 # miniatura da câmera mostrada no jogo
CAMERA_SIZE = (640, 480)


# ----------------------------------------------------------------- pontos do corpo
def torso_center(landmarks: Sequence) -> Optional[Center]:
    """Centro (x, y) normalizado do tronco, ou None se o corpo não estiver visível.

    Usa só os pontos visíveis (confiança >= 0,5). Precisa de pelo menos dois
    pontos: com um só, o centro pularia para qualquer lado.
    """
    if not landmarks:
        return None
    points = [landmarks[i] for i in TORSO_LANDMARKS if i < len(landmarks)]
    visible = [p for p in points if getattr(p, "visibility", 1.0) >= MIN_VISIBILITY]
    if len(visible) < 2:
        return None
    x = sum(p.x for p in visible) / len(visible)
    y = sum(p.y for p in visible) / len(visible)
    return (x, y)


def hands_raised(landmarks: Sequence) -> Hands:
    """Diz quais mãos estão levantadas: pulso acima do ombro do mesmo lado."""
    if not landmarks or len(landmarks) <= max(WRIST.values()):
        return (False, False)
    result = []
    for side in ("left", "right"):
        shoulder = landmarks[SHOULDER[side]]
        wrist = landmarks[WRIST[side]]
        seen = min(getattr(shoulder, "visibility", 1.0), getattr(wrist, "visibility", 1.0))
        # y da imagem cresce para baixo: pulso mais alto tem y menor
        result.append(seen >= MIN_VISIBILITY and wrist.y < shoulder.y - RAISE_MARGIN)
    return (result[0], result[1])


def hand_point(landmarks: Sequence) -> Optional[Center]:
    """Posição (x, y) do pulso da mão do modo "uma mão", ou None se não estiver visível."""
    index = WRIST[HAND]
    if not landmarks or len(landmarks) <= index:
        return None
    wrist = landmarks[index]
    if getattr(wrist, "visibility", 1.0) < MIN_VISIBILITY:
        return None
    return (wrist.x, wrist.y)


def control_hand_raised(hands: Hands) -> bool:
    """A mão do modo "uma mão" está levantada."""
    return hands[1] if HAND == "right" else hands[0]


def _shape(delta: float, dead: float, full: float) -> float:
    """Zona morta em torno do repouso e saturação em ±1 depois de ``full``."""
    size = abs(delta)
    if size <= dead:
        return 0.0
    value = min(1.0, (size - dead) / max(1e-6, full - dead))
    return value if delta > 0 else -value


def _median(values: List[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


# ----------------------------------------------------------------- eixos
class PoseMapper:
    """Transforma o ponto acompanhado (tronco) em eixos (ax: direita, ay: subir).

    Não usa câmera nem MediaPipe: recebe os pontos já detectados. Por isso
    pode ser testado sem webcam.

    Attributes
    ----------
    samples : list
        Pontos colhidos durante a calibração.
    base : tuple | None
        Posição de repouso (x, y), definida quando a calibração termina.
    ax, ay : float
        Eixos atuais, suavizados, em -1..1.
    """

    CALIBRATION_SAMPLES = 40     # leituras com o ponto visível (cerca de 2 s)
    RANGE_X = 0.06               # deslocamento lateral (fração da largura) que vale o máximo
    RANGE_Y = 0.05               # subida/descida (fração da altura) que vale o máximo
    DEAD_X = 0.012               # tremor abaixo disso é ignorado
    DEAD_Y = 0.012
    SMOOTHING = 0.35             # 0..1: quanto maior, mais rápido o avião responde
    LOST_DECAY = 0.85            # a cada leitura sem o ponto, os eixos voltam ao centro

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        """Recomeça a calibração."""
        self.samples: list = []
        self.base: Optional[Center] = None
        self.ax = 0.0
        self.ay = 0.0

    @property
    def calibrated(self) -> bool:
        return self.base is not None

    @property
    def progress(self) -> float:
        if self.calibrated:
            return 1.0
        return min(1.0, len(self.samples) / self.CALIBRATION_SAMPLES)

    def feed(self, center: Optional[Center]) -> None:
        """Uma leitura nova: o ponto acompanhado, ou None se não foi visto."""
        if not self.calibrated:
            if center is not None:
                self.samples.append(center)
                if len(self.samples) >= self.CALIBRATION_SAMPLES:
                    # mediana: uma leitura ruim durante a calibração não desloca o repouso
                    self.base = (_median([c[0] for c in self.samples]),
                                 _median([c[1] for c in self.samples]))
            return
        if center is None:
            self.ax *= self.LOST_DECAY
            self.ay *= self.LOST_DECAY
            return
        dx = center[0] - self.base[0]
        dy = self.base[1] - center[1]          # y da imagem cresce para baixo; subir é positivo
        target_x = _shape(dx, self.DEAD_X, self.RANGE_X)
        target_y = _shape(dy, self.DEAD_Y, self.RANGE_Y)
        self.ax += (target_x - self.ax) * self.SMOOTHING
        self.ay += (target_y - self.ay) * self.SMOOTHING

    def axes(self) -> Tuple[float, float]:
        """Eixos atuais. Zero enquanto a calibração não terminou."""
        if not self.calibrated:
            return (0.0, 0.0)
        return (self.ax, self.ay)


class HandMapper(PoseMapper):
    """Mesmo cálculo do PoseMapper, com limites para o pulso (que se move mais que o tronco)."""

    RANGE_X = 0.10
    RANGE_Y = 0.08
    DEAD_X = 0.015
    DEAD_Y = 0.015


# ----------------------------------------------------------------- gestos de menu
class MenuNavigator:
    """Modo corpo: inclinações e mãos levantadas viram eventos de menu, um por gesto.

    Inclinar passa de "neutro" para "lado" e dispara uma vez; só volta a
    disparar depois de voltar ao centro (histerese), para não repetir sem parar.
    A mão precisa ficar levantada por ``HAND_HOLD_READINGS`` leituras antes de
    contar, e só conta de novo depois de abaixar.

    Eventos: "left", "right", "up", "down", "left_hand", "right_hand".
    """

    ON = 0.6                     # inclinação que dispara o passo
    OFF = 0.3                    # precisa voltar abaixo disso para poder disparar de novo
    HAND_HOLD_READINGS = 10      # ~0,3 s com a mão levantada

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._axis = {"x": 0, "y": 0}          # 1: lado positivo, -1: negativo, 0: neutro
        self._hold = {"left": 0, "right": 0}

    def step(self, ax: float, ay: float, hands: Hands) -> List[str]:
        events: List[str] = []
        for name, value, positive, negative in (("x", ax, "right", "left"), ("y", ay, "up", "down")):
            state = self._axis[name]
            if state == 0:
                if value >= self.ON:
                    state = 1
                    events.append(positive)
                elif value <= -self.ON:
                    state = -1
                    events.append(negative)
            elif state == 1 and value < self.OFF:
                state = 0
            elif state == -1 and value > -self.OFF:
                state = 0
            self._axis[name] = state
        for side, up in zip(("left", "right"), hands):
            if up:
                self._hold[side] += 1
                if self._hold[side] == self.HAND_HOLD_READINGS:
                    events.append(f"{side}_hand")
            else:
                self._hold[side] = 0
        return events


class HandNavigator:
    """Modo uma mão: a posição da mão vira gestos de menu, um evento por gesto.

    A mão precisa ficar numa zona (esquerda, direita, cima, baixo ou levantada)
    por ``DWELL`` leituras antes de contar, para não disparar com um movimento de
    passagem (por exemplo, ao levantar a mão ela atravessa a zona "cima").
    Depois do evento, a zona só conta de novo depois de a mão voltar ao centro.
    Baixar a mão exige um movimento maior e mais tempo, porque é o gesto que
    mais se confunde com relaxar o braço.

    Eventos: "left", "right", "up", "down", "raised".
    """

    ON = {"left": 0.6, "right": 0.6, "up": 0.6, "down": 0.85}
    OFF = 0.3                    # voltar abaixo disso conta como centro
    DWELL = {"left": 10, "right": 10, "up": 10, "down": 20, "raised": 10}   # leituras (~0,3 s; baixar ~0,7 s)

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._zone_now = "center"
        self._count = 0
        self._fired = False

    def _zone(self, ax: float, ay: float, raised: bool) -> str:
        if raised:
            return "raised"
        scores = {}
        if ax >= self.ON["right"]:
            scores["right"] = ax / self.ON["right"]
        if ax <= -self.ON["left"]:
            scores["left"] = -ax / self.ON["left"]
        if ay >= self.ON["up"]:
            scores["up"] = ay / self.ON["up"]
        if ay <= -self.ON["down"]:
            scores["down"] = -ay / self.ON["down"]
        if scores:
            return max(scores, key=scores.get)
        if max(abs(ax), abs(ay)) <= self.OFF:
            return "center"
        return self._zone_now                  # entre OFF e ON: mantém a zona (histerese)

    def step(self, ax: float, ay: float, raised: bool) -> List[str]:
        zone = self._zone(ax, ay, raised)
        if zone != self._zone_now:
            self._zone_now = zone
            self._count = 0
            self._fired = False
        if zone == "center":
            self._fired = False
            return []
        self._count += 1
        if not self._fired and self._count >= self.DWELL[zone]:
            self._fired = True
            return [zone]
        return []


# ----------------------------------------------------------------- MediaPipe e câmera
def create_landmarker(model_path: Path):
    """PoseLandmarker do MediaPipe Tasks em modo VIDEO (uma pessoa)."""
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    options = vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    return vision.PoseLandmarker.create_from_options(options)


def detect_pose(landmarker, rgb, timestamp_ms: int):
    """Detecta o corpo numa imagem RGB.

    Devolve (centro do tronco, mãos levantadas, pulso da mão do modo "uma mão",
    miniatura RGB). Os pontos não vistos vêm como None.
    """
    import cv2
    import mediapipe as mp

    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = landmarker.detect_for_video(image, timestamp_ms)
    landmarks = result.pose_landmarks[0] if result.pose_landmarks else None
    center = torso_center(landmarks) if landmarks else None
    hands = hands_raised(landmarks) if landmarks else (False, False)
    wrist = hand_point(landmarks) if landmarks else None
    preview = cv2.resize(rgb, PREVIEW_SIZE, interpolation=cv2.INTER_AREA).tobytes()
    return center, hands, wrist, preview


def detect_center(landmarker, rgb, timestamp_ms: int) -> Tuple[Optional[Center], Hands, bytes]:
    """Versão resumida de ``detect_pose``: (centro do tronco, mãos levantadas, miniatura)."""
    center, hands, _wrist, preview = detect_pose(landmarker, rgb, timestamp_ms)
    return center, hands, preview


class PoseCameraSource:
    """Lê a webcam numa thread separada e guarda a leitura mais recente.

    A thread roda na velocidade da câmera (cerca de 30 quadros por segundo) e o
    jogo lê o último resultado a cada quadro, sem esperar a câmera. Erros
    (câmera ocupada, biblioteca faltando, modelo ausente) ficam em ``error``.

    Parameters
    ----------
    model_path : Path | None
        Arquivo ``pose_landmarker_*.task``. None quando não foi encontrado.
    camera_index : int
        Índice da webcam no OpenCV (0 é a câmera padrão).
    """

    def __init__(self, model_path: Optional[Path], camera_index: int = 0) -> None:
        self.model_path = model_path
        self.camera_index = camera_index
        self.error: Optional[str] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._seq = 0                       # 0: nenhuma leitura ainda
        self._center: Optional[Center] = None
        self._hands: Hands = (False, False)
        self._wrist: Optional[Center] = None
        self._preview: Optional[bytes] = None
        if model_path is None or not Path(model_path).is_file():
            self.error = "modelo de pose não encontrado"

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.error is not None or self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="webcam-pose", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=3.0)
        self._thread = None

    def snapshot(self):
        """(número da leitura, centro do tronco, mãos levantadas, miniatura, pulso da mão)."""
        with self._lock:
            return self._seq, self._center, self._hands, self._preview, self._wrist

    def _publish(self, center, hands, wrist, preview) -> None:
        with self._lock:
            self._seq += 1
            self._center = center
            self._hands = hands
            self._wrist = wrist
            self._preview = preview

    def _run(self) -> None:
        try:
            import cv2
            landmarker = create_landmarker(self.model_path)
        except ImportError:
            self.error = "instale mediapipe e opencv para usar a câmera"
            return
        except Exception as exc:                         # modelo corrompido, runtime etc.
            self.error = f"modelo de pose não carregou ({exc.__class__.__name__})"
            return
        capture = cv2.VideoCapture(self.camera_index)
        if not capture.isOpened():
            capture.release()
            landmarker.close()
            self.error = "não foi possível abrir a webcam"
            return
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_SIZE[0])
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_SIZE[1])
        last_ts = 0
        try:
            while not self._stop.is_set():
                ok, frame = capture.read()
                if not ok:
                    self.error = "a webcam não envia imagem"
                    break
                frame = cv2.flip(frame, 1)               # espelhado: direita do jogador = direita da tela
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                timestamp = max(last_ts + 1, int(time.monotonic() * 1000))
                last_ts = timestamp
                center, hands, wrist, preview = detect_pose(landmarker, rgb, timestamp)
                self._publish(center, hands, wrist, preview)
        except Exception as exc:
            self.error = f"erro na câmera ({exc.__class__.__name__})"
        finally:
            capture.release()
            landmarker.close()


class WebcamControl:
    """Liga a fonte da câmera ao calibrador e ao navegador de gestos do modo escolhido.

    ``source`` precisa ter ``start()``, ``stop()``, ``snapshot()`` e ``error``.
    ``snapshot()`` devolve (seq, centro, mãos, miniatura) e, opcionalmente, o
    pulso da mão como quinto item (necessário no modo "uma mão").
    O teste usa uma fonte falsa com essa mesma forma.
    """

    def __init__(self, source, mode: str = "corpo") -> None:
        if mode not in MODES:
            raise ValueError(f"modo de câmera desconhecido: {mode}")
        self.source = source
        self.mode = mode
        self.mapper = HandMapper() if mode == "mao" else PoseMapper()
        self.navigator = HandNavigator() if mode == "mao" else MenuNavigator()
        self.preview: Optional[bytes] = None
        self.person_visible = False
        self.hand_visible = False
        self.hands: Hands = (False, False)
        self._seq = -1
        self._frames = 0
        self._events: List[str] = []

    @property
    def error(self) -> Optional[str]:
        return self.source.error

    @property
    def receiving(self) -> bool:
        """True depois que a câmera entregou pelo menos uma leitura."""
        return self._frames > 0

    @property
    def tracked_visible(self) -> bool:
        """O que este modo acompanha (corpo ou mão) está visível."""
        return self.hand_visible if self.mode == "mao" else self.person_visible

    def start(self) -> None:
        self.source.start()

    def stop(self) -> None:
        self.source.stop()

    def restart_calibration(self) -> None:
        self.mapper.reset()
        self.navigator.reset()
        self._events.clear()

    def poll(self) -> None:
        """Consome a leitura nova da câmera, se houver. Chamado a cada quadro do jogo."""
        snap = self.source.snapshot()
        seq, center, hands, preview = snap[:4]
        wrist = snap[4] if len(snap) > 4 else None
        if seq == 0 or seq == self._seq:          # 0: a câmera ainda não entregou nada
            return
        self._seq = seq
        self._frames += 1
        self.person_visible = center is not None
        self.hand_visible = wrist is not None
        self.hands = hands
        self.preview = preview
        if self.mode == "mao":
            self.mapper.feed(wrist)
            ax, ay = self.mapper.axes()
            self._events.extend(self.navigator.step(ax, ay, control_hand_raised(hands)))
        else:
            self.mapper.feed(center)
            ax, ay = self.mapper.axes()
            self._events.extend(self.navigator.step(ax, ay, hands))

    def take_events(self) -> List[str]:
        """Gestos de menu desde a última chamada."""
        events, self._events = self._events, []
        return events

    def axes(self) -> Tuple[float, float]:
        return self.mapper.axes()

    @property
    def calibrated(self) -> bool:
        return self.mapper.calibrated

    @property
    def progress(self) -> float:
        return self.mapper.progress
