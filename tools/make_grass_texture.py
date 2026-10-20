"""
Gera a textura de grama do chão (vista de cima) usada nas eras III e IV.

A imagem é contínua nas bordas (pode ser repetida sem emenda) porque o ruído
é filtrado no domínio da frequência, que é periódico por natureza.

Uso:
    python tools/make_grass_texture.py [--out assets/ground/grass.png] [--seed 7]

Requer: numpy, Pillow (só para gerar a imagem; o jogo não precisa).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

WIDTH, HEIGHT = 256, 128      # u (largura, eixo x do mundo) × v (profundidade)


def periodic_noise(rng: np.random.Generator, shape, scale: float) -> np.ndarray:
    """Ruído suave e periódico: ruído branco filtrado por um passa-baixa gaussiano."""
    white = rng.standard_normal(shape)
    fy = np.fft.fftfreq(shape[0])[:, None]
    fx = np.fft.fftfreq(shape[1])[None, :]
    filt = np.exp(-(fx ** 2 + fy ** 2) * (scale ** 2))
    smooth = np.real(np.fft.ifft2(np.fft.fft2(white) * filt))
    smooth -= smooth.min()
    return smooth / max(smooth.max(), 1e-9)


def make_grass(seed: int) -> Image.Image:
    rng = np.random.default_rng(seed)
    shape = (HEIGHT, WIDTH)
    broad = periodic_noise(rng, shape, 18.0)      # manchas grandes (claro/escuro)
    clumps = periodic_noise(rng, shape, 6.0)      # tufos
    fine = periodic_noise(rng, shape, 1.2)        # textura de folhas

    dark = np.array([46, 104, 40], dtype=np.float32)
    light = np.array([118, 178, 70], dtype=np.float32)
    golden = np.array([170, 186, 80], dtype=np.float32)

    mix = 0.45 * broad + 0.35 * clumps + 0.20 * fine
    mix = np.clip((mix - 0.2) / 0.6, 0.0, 1.0)[..., None]
    rgb = dark * (1 - mix) + light * mix
    # Toques dourados (sol do Art Nouveau) nas áreas mais claras.
    warm = np.clip((broad - 0.6) / 0.4, 0.0, 1.0)[..., None] * 0.35
    rgb = rgb * (1 - warm) + golden * warm

    # Folhas: pontos claros e escuros espalhados.
    speck = rng.random(shape)
    rgb[speck > 0.93] *= 1.22
    rgb[speck < 0.06] *= 0.72

    # Flores pequenas e esparsas (amarelo, rosa e branco), com 2 px de largura.
    flowers = [(255, 213, 79), (244, 143, 177), (250, 250, 240)]
    for _ in range(70):
        y, x = int(rng.integers(0, HEIGHT)), int(rng.integers(0, WIDTH))
        color = np.array(flowers[int(rng.integers(0, len(flowers)))], dtype=np.float32)
        for dx in (0, 1):
            rgb[y, (x + dx) % WIDTH] = color

    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parents[1] / "assets" / "ground" / "grass.png")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    make_grass(args.seed).save(args.out, optimize=True)
    print(f"Textura de grama: {args.out}  ({WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()
