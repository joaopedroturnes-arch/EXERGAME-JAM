"""
Extrai sprites dos aviões de papel e do piloto (boneco) a partir do
"Estúdio 3D Aviões, 14-Bis & Piloto Customizável" (HTML com three.js).

O HTML é aberto num Chromium sem janela (Playwright); cada um dos 11 aviões é
renderizado com o próprio motor three.js do estúdio, com fundo transparente:

  assets/plane_sprites/<modelo>__<piloto>.png      vista de trás (usada no jogo)
  assets/plane_menu/<modelo>__<piloto>.png         vista 3/4 (hangar)
  assets/plane_paint/<modelo>__<piloto>.png        camada de pintura da vista de trás
  assets/plane_menu_paint/<modelo>__<piloto>.png   camada de pintura da vista 3/4
  assets/plane_sprites/catalog.json                nomes dos modelos e pilotos

A camada de pintura é o papel do avião renderizado em branco, só nos pixels em
que o papel aparece (o piloto e as peças que não são de papel ficam de fora).
O jogo multiplica essa camada pela cor escolhida na Oficina de pintura e a
desenha sobre o sprite original. As quatro imagens de uma combinação usam a
mesma câmera e o mesmo recorte, então se encaixam pixel a pixel.

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

RENDER_JS = r"""
async ({key, pilot, view, size}) => {
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

  // 1) Original: cores padrão do estúdio (as "da foto").
  const original = shot();

  // 2) Papel em branco liso: base que o jogo tinge com a cor escolhida.
  const state = modelColorState[key];
  const saved = Object.assign({}, state);
  Object.assign(state, { scheme: 'solid', hex: '#ffffff', secondaryHex: '#ffffff', finish: 'paper' });
  refreshModelVisuals(key);
  const white = shot();
  Object.assign(state, saved);
  refreshModelVisuals(key);

  // 3) Máscara: papel do avião em branco, todo o resto (piloto, rodas, hastes) em preto.
  const paperMat = getMaterialMap()[key];
  const paperTex = modelTextures[key];
  const isPaper = m => !!m && (m === paperMat || (paperTex && m.map === paperTex));
  const whiteMat = new THREE.MeshBasicMaterial({ color: 0xffffff, side: THREE.DoubleSide });
  const blackMat = new THREE.MeshBasicMaterial({ color: 0x000000, side: THREE.DoubleSide });
  const blackLine = new THREE.LineBasicMaterial({ color: 0x000000 });
  const swapped = [];
  target.traverse(o => {
    if (!o.material) return;
    swapped.push([o, o.material]);
    if (o.isLine || o.isLineSegments) { o.material = blackLine; return; }
    const m = o.material;
    const paper = Array.isArray(m) ? m.some(isPaper) : isPaper(m);
    o.material = paper ? whiteMat : blackMat;
  });
  const mask = shot();
  swapped.forEach(([o, m]) => { o.material = m; });
  return { original, white, mask };
}
"""


def decode(data_url: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(data_url.split(",", 1)[1]))).convert("RGBA")


def fit(img: Image.Image, bbox, max_side: int) -> Image.Image:
    """Recorta pelo contorno do sprite original e ajusta ao tamanho final (mesma conta para as camadas)."""
    if bbox:
        img = img.crop(bbox)
    img = img.copy()
    img.thumbnail((max_side - 8, max_side - 8), Image.LANCZOS)
    canvas = Image.new("RGBA", (img.width + 8, img.height + 8), (0, 0, 0, 0))
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
    args = parser.parse_args()

    three_js = args.three.read_bytes()
    jszip_js = args.jszip.read_bytes()
    folders = {
        "back": (args.out / "plane_sprites", args.out / "plane_paint", args.game_size),
        "menu": (args.out / "plane_menu", args.out / "plane_menu_paint", args.menu_size),
    }
    for sprite_dir, paint_dir, _ in folders.values():
        sprite_dir.mkdir(parents=True, exist_ok=True)
        paint_dir.mkdir(parents=True, exist_ok=True)

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

        for pilot in args.pilots:
            for key in args.models:
                for view, (sprite_dir, paint_dir, size) in folders.items():
                    shots = page.evaluate(RENDER_JS, {"key": key, "pilot": pilot, "view": view, "size": 640})
                    original = decode(shots["original"])
                    bbox = original.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
                    fit(original, bbox, size).save(sprite_dir / f"{key}__{pilot}.png", optimize=True)
                    paint = paint_layer(decode(shots["white"]), decode(shots["mask"]))
                    fit(paint, bbox, size).save(paint_dir / f"{key}__{pilot}.png", optimize=True)
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
