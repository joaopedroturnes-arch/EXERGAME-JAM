"""
Gera a textura de concreto sujo do chão (vista de cima) das áreas ainda não
restauradas: placas com juntas transversais, manchas de óleo, rachaduras,
fuligem e pontos de ferrugem.

A imagem é contínua nas bordas (ruído periódico e desenhos com coordenadas
"dando a volta"), então pode ser repetida sem emenda. As juntas paralelas à
pista são desenhadas pelo jogo em perspectiva, não fazem parte da imagem.

Uso:
    python tools/make_concrete_texture.py [--out assets/ground/concrete.png] [--seed 11]

Requer: numpy, Pillow (só para gerar a imagem; o jogo não precisa).
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
from PIL import Image

WIDTH, HEIGHT = 256, 128      # u (largura, eixo x do mundo) × v (profundidade)
SLAB_ROWS = 64                # duas placas por repetição da textura


def periodic_noise(rng: np.random.Generator, shape, scale: float) -> np.ndarray:
    white = rng.standard_normal(shape)
    fy = np.fft.fftfreq(shape[0])[:, None]
    fx = np.fft.fftfreq(shape[1])[None, :]
    smooth = np.real(np.fft.ifft2(np.fft.fft2(white) * np.exp(-(fx ** 2 + fy ** 2) * scale ** 2)))
    smooth -= smooth.min()
    return smooth / max(smooth.max(), 1e-9)


def wrapped_distance(size: int, center: float) -> np.ndarray:
    d = np.abs(np.arange(size) - center)
    return np.minimum(d, size - d)


def make_concrete(seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    shape = (HEIGHT, WIDTH)
    mottle = periodic_noise(rng, shape, 14.0)
    grime = periodic_noise(rng, shape, 32.0)
    fine = periodic_noise(rng, shape, 1.0)

    base = np.array([118, 112, 103], dtype=np.float32)       # concreto claro
    dirt = np.array([92, 76, 58], dtype=np.float32)          # terra / fuligem marrom
    shade = 0.70 + 0.40 * (0.6 * mottle + 0.4 * fine)
    rgb = base * shade[..., None]
    dirty = np.clip((grime - 0.45) / 0.45, 0.0, 1.0)[..., None] * 0.65
    rgb = rgb * (1 - dirty) + dirt * shade[..., None] * dirty

    # Cada placa com um tom levemente diferente.
    rgb[SLAB_ROWS:] *= 0.93

    # Agregado do concreto: pontinhos claros e escuros.
    speck = rng.random(shape)
    rgb[speck > 0.95] *= 1.18
    rgb[speck < 0.05] *= 0.78

    # Manchas de óleo: bordas irregulares e escurecimento forte no centro.
    edge_noise = periodic_noise(rng, shape, 3.0)
    oil = np.array([30, 27, 24], dtype=np.float32)
    for _ in range(8):
        cx, cy = rng.uniform(0, WIDTH), rng.uniform(0, HEIGHT)
        rx, ry = rng.uniform(9, 26), rng.uniform(6, 16)
        dx = wrapped_distance(WIDTH, cx)[None, :] / rx
        dy = wrapped_distance(HEIGHT, cy)[:, None] / ry
        r = np.sqrt(dx ** 2 + dy ** 2) + (edge_noise - 0.5) * 0.6
        strength = (np.clip(1.0 - r, 0.0, 1.0) ** 0.6 * rng.uniform(0.55, 0.85))[..., None]
        rgb = rgb * (1 - strength) + oil * strength

    # Rachaduras: caminhos aleatórios finos.
    for _ in range(7):
        x, y = rng.uniform(0, WIDTH), rng.uniform(0, HEIGHT)
        angle = rng.uniform(0, 2 * math.pi)
        for _ in range(int(rng.integers(35, 95))):
            angle += rng.normal(0, 0.35)
            x, y = (x + math.cos(angle)) % WIDTH, (y + math.sin(angle) * 0.8) % HEIGHT
            rgb[int(y), int(x)] *= 0.5

    # Juntas transversais entre as placas (com uma aresta clara logo depois).
    for row in (0, SLAB_ROWS):
        rgb[row] *= 0.42
        rgb[(row + 1) % HEIGHT] *= 0.62
        rgb[(row + 2) % HEIGHT] *= 1.08

    # Ferrugem e restos metálicos espalhados.
    rust = [(150, 78, 38), (120, 60, 30), (70, 64, 58)]
    for _ in range(90):
        y, x = int(rng.integers(0, HEIGHT)), int(rng.integers(0, WIDTH))
        color = np.array(rust[int(rng.integers(0, len(rust)))], dtype=np.float32)
        rgb[y, x] = color
        if rng.random() < 0.4:
            rgb[y, (x + 1) % WIDTH] = color

    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parents[1] / "assets" / "ground" / "concrete.png")
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    make_concrete(args.seed).save(args.out, optimize=True)
    print(f"Textura de concreto: {args.out}  ({WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()
