"""
Extrai sprites dos aviões de papel e do piloto (boneco) a partir do
"Estúdio 3D Aviões, 14-Bis & Piloto Customizável" (HTML com three.js).

O HTML é aberto num Chromium sem janela (Playwright); cada um dos 11 aviões é
renderizado com o próprio motor three.js do estúdio, com fundo transparente:

  assets/plane_sprites/<modelo>__<piloto>.png      vista de trás (usada no jogo)
  assets/plane_menu/<modelo>__<piloto>.png         vista 3/4 (hangar)
  assets/plane_paint/<modelo>__<piloto>.png        camada de pintura da vista de trás
  assets/plane_menu_paint/<modelo>__<piloto>.png   camada de pintura da vista 3/4
  assets/plane_uv/<modelo>__<piloto>.png           mapa UV do papel (vista de trás)
  assets/plane_menu_uv/<modelo>__<piloto>.png      mapa UV do papel (vista 3/4)
  assets/plane_patterns/<padrão>.png               texturas dos padrões de pintura do estúdio
  assets/plane_sprites/catalog.json                nomes dos modelos e pilotos

A camada de pintura é o papel do avião renderizado em branco, só nos pixels em
que o papel aparece (o piloto e as peças que não são de papel ficam de fora).
O jogo multiplica essa camada pela cor escolhida na Oficina de pintura e a
desenha sobre o sprite original. As imagens de uma combinação usam a mesma
câmera e o mesmo recorte, então se encaixam pixel a pixel.

O mapa UV guarda, em cada pixel do papel, a coordenada da textura do estúdio
(R = coluna, G = linha da imagem, de 0 a 255). Com ele o jogo "veste" o avião
com os padrões de pintura do estúdio (camuflado, chamas, galáxia...) sem
precisar de uma imagem por padrão e por combinação: basta consultar a textura
do padrão (256×256) pixel a pixel. As texturas são desenhadas pela própria
função drawSchemeBackground do estúdio, com as cores dos presets dele.

Para só acrescentar os mapas UV e os padrões a um conjunto já extraído:
    python tools/extract_planes.py ... --passes uv

<piloto> = none | riding | surfing | zen | waving | superman | wheelchair

Uso (somente para gerar os assets; o jogo não precisa do Playwright):
    python tools/extract_planes.py --html CAMINHO/estudio_avioes_14bis_e_piloto_3d.html \
        --three node_modules/three/build/three.min.js --jszip node_modules/jszip/dist/jszip.min.js
"""

from __future__ import annotations

import argparse
import base64
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
from playwright.sync_api import sync_playwright

MODEL_KEYS = ["dart", "glider", "stubby", "binder", "needle", "hoverboard",
              "crane", "accordion", "jetfighter", "tailboom", "bis14"]
PILOTS = ["none", "riding", "surfing", "zen", "waving", "superman", "wheelchair"]
PILOT_LABELS = {
    "none": "Sem piloto", "riding": "Montado", "surfing": "Surfando", "zen": "Zen",
    "waving": "Acenando", "superman": "Super-herói", "wheelchair": "Cadeira de rodas",
}

# Padrões de pintura: (chave do jogo, esquema do estúdio, cor 1, cor 2), tirados dos presets do estúdio.
PATTERNS = [
    ("camuflado", "camo", "#365314", "#14532d"),
    ("deserto", "camo", "#d6bc8b", "#78350f"),
    ("artico", "camo", "#e2e8f0", "#334155"),
    ("chamas", "flames", "#111827", "#ef4444"),
    ("plasma", "flames", "#090d16", "#3b82f6"),
    ("galaxia", "galaxy", "#1e1b4b", "#a855f7"),
    ("cyberpunk", "cyberpunk", "#0f172a", "#ec4899"),
    ("tigre", "tiger", "#f59e0b", "#111827"),
    ("hexagonal", "carbon", "#090d16", "#10b981"),
    ("prisma", "dazzle", "#0284c7", "#f43f5e"),
    ("xadrez", "checkered", "#f8fafc", "#111827"),
    ("listras", "racing_stripes", "#2563eb", "#f8fafc"),
    ("raios", "sunburst", "#fef08a", "#ea580c"),
    ("pop_art", "halftone", "#fde047", "#dc2626"),
    ("brasil", "wingtips", "#fde047", "#16a34a"),
]

PATTERN_JS = r"""
({scheme, hex, secondaryHex, size}) => {
  const big = document.createElement('canvas');
  big.width = 1024; big.height = 1024;
  drawSchemeBackground(big.getContext('2d'), { scheme, hex, secondaryHex, finish: 'paper' });
  const small = document.createElement('canvas');
  small.width = size; small.height = size;
  const ctx = small.getContext('2d');
  ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(big, 0, 0, size, size);
  return small.toDataURL('image/png');
}
"""

RENDER_JS = r"""
async ({key, pilot, view, size, passes}) => {
  isFlightActive = false; isAutoRotate = false;
  if (windLinesGroup) windLinesGroup.visible = false;
  const wantPilot = pilot !== 'none';
  if (wantPilot && stickmanConfig.pose !== pilot) {
    stickmanConfig.pose = pilot;
    stickmanConfig.mobility = pilot === 'wheelchair' ? 'wheelchair' : 'none';
    rebuildAllStickmen();
  }
  stickmanConfig.enabled = wantPilot;
  const groups = getGroupMap();
  for (const k of ALL_MODEL_KEYS) {
    const g = groups[k];
    g.visible = (k === key);
    g.position.set(0, 0, 0); g.rotation.set(0, 0, 0);
    const inst = stickmanInstances[k];
    if (inst && inst.root) {
      inst.root.visible = wantPilot;
      if (inst.headGroup) inst.headGroup.rotation.set(0, 0, 0);
      if (inst.wavingArmPivot) inst.wavingArmPivot.rotation.z = 0.25;
      (inst.scarfSegments || []).forEach(s => { s.rotation.set(0.14, 0, 0); });
    }
  }
  scene.background = null;
  const target = groups[key];
  target.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(target);
  const center = box.getCenter(new THREE.Vector3());
  const radius = box.getSize(new THREE.Vector3()).length() / 2;

  if (!window.__spriteRenderer) {
    window.__spriteRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
  }
  const r = window.__spriteRenderer;
  r.setPixelRatio(1); r.setSize(size, size); r.setClearColor(0x000000, 0);
  const cam = new THREE.PerspectiveCamera(18, 1, 0.1, 200);
  const dist = radius / Math.sin((18 * Math.PI / 180) / 2) * 1.05;
  let dir;
  if (view === 'back') {
    // atrás e um pouco acima: o jogador vê o avião voando para dentro da tela
    const pitch = 14 * Math.PI / 180;
    dir = new THREE.Vector3(0, Math.sin(pitch), -Math.cos(pitch));
  } else {
    const yaw = 38 * Math.PI / 180, pitch = 22 * Math.PI / 180;
    dir = new THREE.Vector3(Math.sin(yaw) * Math.cos(pitch), Math.sin(pitch), Math.cos(yaw) * Math.cos(pitch));
  }
  cam.position.copy(center).addScaledVector(dir, dist);
  cam.lookAt(center);
  const shot = () => { r.render(scene, cam); return r.domElement.toDataURL('image/png'); };
  const out = {};

  // 1) Original: cores padrão do estúdio (as "da foto"). Sempre: define o recorte.
  out.original = shot();

  const paperMat = getMaterialMap()[key];
  const paperTex = modelTextures[key];
  const isPaper = m => !!m && (m === paperMat || (paperTex && m.map === paperTex));
  const swapMaterials = (paperMaterial, otherMaterial, lineMaterial) => {
    const swapped = [];
    target.traverse(o => {
      if (!o.material) return;
      swapped.push([o, o.material]);
      if (o.isLine || o.isLineSegments) { o.material = lineMaterial; return; }
      const m = o.material;
      const paper = Array.isArray(m) ? m.some(isPaper) : isPaper(m);
      o.material = paper ? paperMaterial : otherMaterial;
    });
    return () => swapped.forEach(([o, m]) => { o.material = m; });
  };
  const blackMat = new THREE.MeshBasicMaterial({ color: 0x000000, side: THREE.DoubleSide });
  const blackLine = new THREE.LineBasicMaterial({ color: 0x000000 });

  if (passes.includes('paint')) {
  // 2) Papel em branco liso: base que o jogo tinge com a cor escolhida.
  const state = modelColorState[key];
  const saved = Object.assign({}, state);
  Object.assign(state, { scheme: 'solid', hex: '#ffffff', secondaryHex: '#ffffff', finish: 'paper' });
  refreshModelVisuals(key);
  out.white = shot();
  Object.assign(state, saved);
  refreshModelVisuals(key);

  // 3) Máscara: papel do avião em branco, todo o resto (piloto, rodas, hastes) em preto.
  const whiteMat = new THREE.MeshBasicMaterial({ color: 0xffffff, side: THREE.DoubleSide });
  const restore = swapMaterials(whiteMat, blackMat, blackLine);
  out.mask = shot();
  restore();
  }

  if (passes.includes('uv')) {
    // 4) Mapa UV: R = coluna e G = linha da textura do papel (a textura do estúdio
    // repete e é carregada de cabeça para baixo, daí fract() e 1 - v).
    const uvMat = new THREE.ShaderMaterial({
      side: THREE.DoubleSide,
      vertexShader: 'varying vec2 vUv; void main() { vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
      fragmentShader: 'varying vec2 vUv; void main() { vec2 f = fract(vUv); gl_FragColor = vec4(f.x, 1.0 - f.y, 1.0, 1.0); }',
    });
    const restore = swapMaterials(uvMat, blackMat, blackLine);
    r.setClearColor(0x000000, 1);
    // Sem suavização: a média de duas coordenadas na borda não é uma coordenada válida.
    if (!window.__uvRenderer) {
      window.__uvRenderer = new THREE.WebGLRenderer({ antialias: false, alpha: false, preserveDrawingBuffer: true });
    }
    const ru = window.__uvRenderer;
    ru.setPixelRatio(1); ru.setSize(size, size); ru.setClearColor(0x000000, 1);
    ru.outputEncoding = THREE.LinearEncoding; ru.toneMapping = THREE.NoToneMapping;
    ru.render(scene, cam);
    out.uv = ru.domElement.toDataURL('image/png');
    r.setClearColor(0x000000, 0);
    restore();
  }
  return out;
}
"""


def decode(data_url: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(data_url.split(",", 1)[1]))).convert("RGBA")


def fit(img: Image.Image, bbox, max_side: int, resample=Image.LANCZOS) -> Image.Image:
    """Recorta pelo contorno do sprite original e ajusta ao tamanho final (mesma conta para as camadas)."""
    if bbox:
        img = img.crop(bbox)
    img = img.copy()
    # reducing_gap=None: sem pré-redução por média (estragaria o mapa UV no modo NEAREST).
    img.thumbnail((max_side - 8, max_side - 8), resample,
                  reducing_gap=None if resample == Image.NEAREST else 2.0)
    canvas = Image.new(img.mode, (img.width + 8, img.height + 8), (0, 0, 0, 0) if img.mode == "RGBA" else (0, 0, 0))
    canvas.paste(img, (4, 4))
    return canvas


def paint_layer(white: Image.Image, mask: Image.Image) -> Image.Image:
    """Papel em branco com transparência = cobertura do papel visível na máscara."""
    w = np.asarray(white, dtype=np.float32)
    m = np.asarray(mask, dtype=np.float32)
    coverage = (m[..., 0] / 255.0) * (m[..., 3] / 255.0)       # branco × opacidade da máscara
    out = np.dstack([w[..., :3], coverage * 255.0])
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--three", type=Path, required=True)
    parser.add_argument("--jszip", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "assets")
    parser.add_argument("--game-size", type=int, default=300)
    parser.add_argument("--menu-size", type=int, default=260)
    parser.add_argument("--models", nargs="*", default=MODEL_KEYS, help="só estes modelos (padrão: todos)")
    parser.add_argument("--pilots", nargs="*", default=PILOTS, help="só estes pilotos (padrão: todos)")
    parser.add_argument("--passes", nargs="*", default=["sprites", "paint", "uv"],
                        choices=["sprites", "paint", "uv"],
                        help="o que gravar: sprites originais, camadas de pintura, mapas UV (padrão: tudo)")
    parser.add_argument("--pattern-size", type=int, default=256)
    args = parser.parse_args()

    three_js = args.three.read_bytes()
    jszip_js = args.jszip.read_bytes()
    folders = {
        "back": (args.out / "plane_sprites", args.out / "plane_paint", args.out / "plane_uv", args.game_size),
        "menu": (args.out / "plane_menu", args.out / "plane_menu_paint", args.out / "plane_menu_uv", args.menu_size),
    }
    for sprite_dir, paint_dir, uv_dir, _ in folders.values():
        for folder in (sprite_dir, paint_dir, uv_dir):
            folder.mkdir(parents=True, exist_ok=True)
    pattern_dir = args.out / "plane_patterns"
    pattern_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        page = browser.new_page(viewport={"width": 1280, "height": 800})

        def route(r):
            url = r.request.url
            if url.endswith("three.min.js"):
                return r.fulfill(body=three_js, content_type="application/javascript")
            if url.endswith("jszip.min.js"):
                return r.fulfill(body=jszip_js, content_type="application/javascript")
            if url.startswith("http"):
                return r.fulfill(body="", content_type="application/javascript")
            return r.continue_()

        page.route("**/*", route)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(args.html.resolve().as_uri())
        page.wait_for_function("typeof bis14Group !== 'undefined' && !!bis14Group", timeout=60000)

        labels = page.evaluate("""() => Object.fromEntries(ALL_MODEL_KEYS.map(k => {
            const el = document.getElementById('btn-' + k);
            const txt = el ? el.innerText.split('\\n').map(s => s.trim()).filter(Boolean) : [];
            return [k, txt.find(t => /^\\d+\\./.test(t)) || txt[0] || k];
        }))""")

        if "uv" in args.passes:
            for name, scheme, hex1, hex2 in PATTERNS:
                data = page.evaluate(PATTERN_JS, {"scheme": scheme, "hex": hex1, "secondaryHex": hex2,
                                                  "size": args.pattern_size})
                decode(data).convert("RGB").save(pattern_dir / f"{name}.png", optimize=True)
            print(f"  {len(PATTERNS)} padrões de pintura", flush=True)

        js_passes = [p for p in args.passes if p in ("paint", "uv")]
        for pilot in args.pilots:
            for key in args.models:
                for view, (sprite_dir, paint_dir, uv_dir, size) in folders.items():
                    shots = page.evaluate(RENDER_JS, {"key": key, "pilot": pilot, "view": view,
                                                      "size": 640, "passes": js_passes})
                    original = decode(shots["original"])
                    bbox = original.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
                    name = f"{key}__{pilot}.png"
                    if "sprites" in args.passes:
                        fit(original, bbox, size).save(sprite_dir / name, optimize=True)
                    if "paint" in args.passes:
                        paint = paint_layer(decode(shots["white"]), decode(shots["mask"]))
                        fit(paint, bbox, size).save(paint_dir / name, optimize=True)
                    if "uv" in args.passes:
                        uv = decode(shots["uv"]).convert("RGB")
                        fit(uv, bbox, size, Image.NEAREST).save(uv_dir / name, optimize=True)
            print(f"  piloto {pilot}: {len(args.models)} aviões", flush=True)
        browser.close()

    catalog = {
        "models": [{"key": k, "label": labels.get(k, k)} for k in MODEL_KEYS],
        "pilots": [{"key": p, "label": PILOT_LABELS[p]} for p in PILOTS],
    }
    (folders["back"][0] / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(catalog, ensure_ascii=False, indent=2))
    if errors:
        print("Avisos da página (ignorados):", *errors[:5], sep="\n  ")


if __name__ == "__main__":
    main()
