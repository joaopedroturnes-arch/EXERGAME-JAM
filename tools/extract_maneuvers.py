"""
Extrai as curvas das manobras do pacote "8 animações 3D" (glTF) para o jogo.

Cada animação do pacote move um avião 3D (posição + rotação em quatérnios).
Este script converte um ciclo de cada manobra em curvas simples, no referencial
do próprio avião no início da manobra:

  roll   giro em torno do eixo do avião (graus, acumulado, sem saltos de 360°)
  pitch  nariz para cima / para baixo (graus, acumulado; positivo = nariz para cima)
  dx     deslocamento lateral   (normalizado: o maior deslocamento da manobra vale 1)
  dy     deslocamento vertical  (idem)
  dz     deslocamento para a frente (idem; positivo = afastando-se da câmera)

O jogo desenha o avião visto de trás, então aplica essas curvas ao sprite 2D:
roll vira rotação, pitch vira achatamento/inversão vertical (no topo do looping
o avião aparece de cabeça para baixo), dx/dy viram deslocamento na tela e dz
vira escala. As manobras são só visuais: a colisão continua na posição real.

Saída: assets/maneuvers/maneuvers.json

Uso:
    python tools/extract_maneuvers.py --gltf-dir CAMINHO/01_Animacoes_3D_Prontas_GLTF_8_Manobras
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import struct
from pathlib import Path

# nome no jogo: (arquivo glTF, início do ciclo em s, fim do ciclo em s ou None = fim da animação, "settle")
# settle=True: a manobra termina na posição normal (curvas relativas ao último quadro).
MANEUVERS = {
    "tonneau": ("animacao_05_Tonneau_Giro_Aileron_360_bis14.gltf", 0.0, "roll360", False),
    "looping": ("animacao_03_Looping_Vertical_Completo_bis14.gltf", 0.0, "pitch360", False),
    "cobra": ("animacao_06_Manobra_Cobra_Rasante_bis14.gltf", 0.0, None, False),
    "decolagem": ("animacao_07_Decolagem_Historica_14Bis_Bagatelle_bis14.gltf", 1.6, None, True),
}
SAMPLES = 49


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def conj(q):
    return (-q[0], -q[1], -q[2], q[3])


def rotate(q, v):
    return qmul(qmul(q, (v[0], v[1], v[2], 0.0)), conj(q))[:3]


def twist(q, axis) -> float:
    """Ângulo (graus) da parte da rotação q em torno de 'axis' (decomposição swing-twist)."""
    d = q[0] * axis[0] + q[1] * axis[1] + q[2] * axis[2]
    return math.degrees(2.0 * math.atan2(d, q[3]))


def slerp(a, b, t):
    dot = sum(x * y for x, y in zip(a, b))
    if dot < 0:
        b, dot = tuple(-x for x in b), -dot
    if dot > 0.9995:
        q = tuple(x + (y - x) * t for x, y in zip(a, b))
    else:
        th = math.acos(dot)
        s = math.sin(th)
        q = tuple((math.sin((1 - t) * th) * x + math.sin(t * th) * y) / s for x, y in zip(a, b))
    n = math.sqrt(sum(x * x for x in q))
    return tuple(x / n for x in q)


def load_tracks(path: Path):
    gltf = json.loads(path.read_text(encoding="utf-8"))
    buffer = base64.b64decode(gltf["buffers"][0]["uri"].split(",", 1)[1])

    def read(index):
        acc = gltf["accessors"][index]
        view = gltf["bufferViews"][acc["bufferView"]]
        n = {"SCALAR": 1, "VEC3": 3, "VEC4": 4}[acc["type"]]
        offset = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
        values = struct.unpack_from(f"<{acc['count'] * n}f", buffer, offset)
        return [tuple(values[i * n:(i + 1) * n]) for i in range(acc["count"])]

    anim = gltf["animations"][0]
    samplers = {c["target"]["path"]: anim["samplers"][c["sampler"]] for c in anim["channels"]}
    times = [t[0] for t in read(samplers["rotation"]["input"])]
    rotations = read(samplers["rotation"]["output"])
    positions = read(samplers["translation"]["output"])
    return times, rotations, positions


def sample(times, values, t, interp):
    if t <= times[0]:
        return values[0]
    for i in range(1, len(times)):
        if t <= times[i]:
            f = (t - times[i - 1]) / max(1e-9, times[i] - times[i - 1])
            return interp(values[i - 1], values[i], f)
    return values[-1]


def lerp3(a, b, f):
    return tuple(x + (y - x) * f for x, y in zip(a, b))


def unwrap(series):
    out, acc, prev = [], 0.0, None
    for v in series:
        if prev is not None:
            acc += (v - prev + 180.0) % 360.0 - 180.0
        prev = v
        out.append(acc)
    return out


def extract(path: Path, start: float, end, settle: bool) -> dict:
    times, rotations, positions = load_tracks(path)
    # 1) acha o fim do ciclo em alta resolução
    fine = [start + i * 0.005 for i in range(int((times[-1] - start) / 0.005) + 1)]
    q0 = sample(times, rotations, start, slerp)
    rel = [qmul(conj(q0), sample(times, rotations, t, slerp)) for t in fine]
    roll_f = unwrap([twist(q, (0, 0, 1)) for q in rel])
    pitch_f = unwrap([twist(q, (1, 0, 0)) for q in rel])
    stop = fine[-1]
    if end == "roll360":
        stop = next((t for t, r in zip(fine, roll_f) if abs(r) >= 360.0), stop)
    elif end == "pitch360":
        stop = next((t for t, p in zip(fine, pitch_f) if abs(p) >= 360.0), stop)
    elif isinstance(end, (int, float)):
        stop = float(end)

    # 2) amostra o ciclo em SAMPLES pontos
    ts = [start + (stop - start) * i / (SAMPLES - 1) for i in range(SAMPLES)]
    p0 = sample(times, positions, start, lerp3)
    rel = [qmul(conj(q0), sample(times, rotations, t, slerp)) for t in ts]
    roll = unwrap([twist(q, (0, 0, 1)) for q in rel])
    pitch = unwrap([twist(q, (1, 0, 0)) for q in rel])
    disp = [rotate(conj(q0), tuple(a - b for a, b in zip(sample(times, positions, t, lerp3), p0))) for t in ts]

    # 3) referencial: "para a frente" é para onde o avião começa a andar
    first = next((d[2] for d in disp if abs(d[2]) > 0.05), 1.0)
    forward = 1.0 if first >= 0 else -1.0
    disp = [(d[0] * forward, d[1], d[2] * forward) for d in disp]
    roll = [r * forward for r in roll]
    pitch = [p * forward for p in pitch]
    peak = max(pitch, key=abs)
    if peak < 0:                       # todas as manobras usadas sobem o nariz
        pitch = [-p for p in pitch]
    if settle:                         # termina na posição normal
        last = disp[-1]
        disp = [tuple(a - b for a, b in zip(d, last)) for d in disp]
        roll = [r - roll[-1] for r in roll]
        pitch = [p - pitch[-1] for p in pitch]
    else:
        # Começa e termina na posição normal: remove a deriva linear do ciclo
        # (no estúdio o avião segue em frente; no jogo ele volta ao lugar).
        n = len(ts) - 1
        last = disp[-1]
        disp = [tuple(a - b * i / n for a, b in zip(d, last)) for i, d in enumerate(disp)]
        def close(angles):
            drift = angles[-1] - round(angles[-1] / 360.0) * 360.0
            return [a - drift * i / n for i, a in enumerate(angles)]
        roll, pitch = close(roll), close(pitch)
    scale = max(1e-6, max(abs(c) for d in disp for c in d))
    rows = []
    for i, (r, p, d) in enumerate(zip(roll, pitch, disp)):
        rows.append([round(i / (SAMPLES - 1), 4), round(r, 2), round(p, 2),
                     round(d[0] / scale, 4), round(d[1] / scale, 4), round(d[2] / scale, 4)])
    return {"source": path.name, "seconds": round(stop - start, 3), "samples": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gltf-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "assets" / "maneuvers")
    args = parser.parse_args()
    data = {"columns": ["t", "roll", "pitch", "dx", "dy", "dz"]}
    for name, (filename, start, end, settle) in MANEUVERS.items():
        data[name] = extract(args.gltf_dir / filename, start, end, settle)
        rows = data[name]["samples"]
        print(f"{name:10s} {data[name]['seconds']:5.2f}s  roll {rows[-1][1]:7.1f}°  "
              f"pitch máx {max(r[2] for r in rows):6.1f}°  ({filename})")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "maneuvers.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
