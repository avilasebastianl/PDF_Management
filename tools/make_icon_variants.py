"""
Genera el logo de la aplicacion (un perrito tierno, inspirado en el perro del
autor) y sus variantes de pelaje en ``assets/icons``:

- ``app.png`` / ``app.ico``: variante "clasico" (pelo crema, como el original).
- ``app_<variante>.png`` / ``.ico``: el resto de variantes.

El dibujo se define como SVG y se rasteriza con PyMuPDF. La bandana cambia de
color cuando hace falta para que contraste con el pelo. Uso::

    venv/Scripts/python.exe tools/make_icon_variants.py
"""

import math
import random
from pathlib import Path

import pymupdf
from PIL import Image

ICONS = Path(__file__).resolve().parents[1] / "assets" / "icons"
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

BASE = {
    "fur": "#E8D6B0",
    "shade": "#C9AD80",
    "muzzle": "#F7EFDF",
    "ear_in": "#EBA5AC",
    "eye": "#2A1A12",
    "nose": "#1C1717",
    "tongue": "#E77A86",
    "bandana": "#23232D",
    "paw": "#F2A33A",
    "paw2": "#FFFFFF",
}

# Variante -> colores que cambian respecto de BASE. Opcionales: brow, mouth, whisker,
# eye_rim y nose_rim (contorno claro de ojos y nariz para que se vean sobre pelo oscuro).
VARIANTS: dict[str, dict[str, str]] = {
    "clasico": {},
    "negro": {
        "fur": "#2F2B2B",
        "shade": "#57504F",
        "muzzle": "#6B6462",
        "ear_in": "#E39AA3",
        "eye": "#0E0A09",
        "nose": "#0B0909",
        "brow": "#8A817D",
        "mouth": "#D2C8C3",
        "whisker": "#8A817D",
        "eye_rim": "#A39A95",
        "nose_rim": "#8A817D",
        # bandana naranja con huellas oscuras: el negro no contrasta con el pelo negro
        "bandana": "#F2A33A",
        "paw": "#23232D",
        "paw2": "#FFFFFF",
    },
    "gris": {"fur": "#A9AAAF", "shade": "#7C7D84", "muzzle": "#DCDDE1"},
    "blanco": {"fur": "#F7F4EE", "shade": "#BDB4A4", "muzzle": "#FFFFFF"},
    "cafe": {
        "fur": "#9A6A44",
        "shade": "#6E4A2D",
        "muzzle": "#D9B790",
        "brow": "#5C3C23",
        # bandana azul petroleo con huellas naranjas: el negro se pierde con el cafe oscuro
        "bandana": "#1F4E63",
    },
}


def _scallop(cx, cy, rx, ry, n, depth, start=0.0, end=360.0, closed=True):
    """Borde de mechones redondeados (curvas cuyo control sale hacia afuera)."""
    pts = []
    for i in range(n + 1):
        a = math.radians(start + (end - start) * i / n)
        pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a), a))
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f} "
    for i in range(n):
        am = (pts[i][2] + pts[i + 1][2]) / 2
        mx, my = cx + (rx + depth) * math.cos(am), cy + (ry + depth) * math.sin(am)
        d += f"Q{mx:.1f},{my:.1f} {pts[i + 1][0]:.1f},{pts[i + 1][1]:.1f} "
    return d + ("Z" if closed else "")


def _shaggy(cx, cy, rx, ry, n, top_depth, side_depth, start=0.0, end=360.0, seed=1):
    """Pelo hirsuto: arriba mechones cortos y redondeados; a los lados y abajo, en punta."""
    rnd = random.Random(seed)
    pts = []
    for i in range(n + 1):
        a = math.radians(start + (end - start) * i / n)
        pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a), a))
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f} "
    for i in range(n):
        x0, y0, a0 = pts[i]
        x1, y1, a1 = pts[i + 1]
        am = (a0 + a1) / 2 + rnd.uniform(-0.06, 0.06)
        top = math.sin(am) < -0.45
        k = (top_depth if top else side_depth) * rnd.uniform(0.7, 1.3)
        tx, ty = cx + (rx + k) * math.cos(am), cy + (ry + k) * math.sin(am)
        if top:
            d += f"Q{tx:.1f},{ty:.1f} {x1:.1f},{y1:.1f} "
        else:
            ty += k * 0.25  # el mechon cae un poco
            d += (
                f"Q{(x0 + tx) / 2:.1f},{(y0 + ty) / 2 + 3:.1f} {tx:.1f},{ty:.1f} "
                f"Q{(tx + x1) / 2:.1f},{(ty + y1) / 2 - 2:.1f} {x1:.1f},{y1:.1f} "
            )
    return d + "Z"


def _paw(x, y, s, color):
    toes = "".join(
        f'<circle cx="{x + dx * s:.1f}" cy="{y + dy * s:.1f}" r="{3 * s:.1f}"/>'
        for dx, dy in ((-8, -4), (-3, -9), (3, -9), (8, -4))
    )
    return f'<g fill="{color}"><ellipse cx="{x}" cy="{y + 4 * s:.1f}" rx="{7 * s:.1f}" ry="{6 * s:.1f}"/>{toes}</g>'


def _bandana(c, top=394):
    d = f"M112,{top} Q256,{top + 46} 400,{top} L306,{top + 88} Q256,{top + 122} 206,{top + 88} Z"
    paws = _paw(178, top + 30, 1.5, c["paw"]) + _paw(256, top + 80, 1.6, c["paw2"]) + _paw(334, top + 30, 1.5, c["paw"])
    # Borde del tono del pelo: la bandana se distingue tambien sobre fondos oscuros.
    edge = f'stroke="{c["shade"]}" stroke-width="5" stroke-linejoin="round"'
    return f'<path d="{d}" fill="{c["bandana"]}" {edge}/>{paws}'


def _ear(side, c):
    def sx(x):
        return x if side == "l" else 512 - x

    outer = f"M{sx(112)},236 Q{sx(98)},120 {sx(132)},44 Q{sx(196)},92 {sx(228)},150 Z"
    tip = f"M{sx(132)},44 Q{sx(150)},60 {sx(166)},74 Q{sx(140)},76 {sx(122)},98 Z"
    inside = f"M{sx(134)},206 Q{sx(128)},130 {sx(146)},88 Q{sx(182)},122 {sx(202)},160 Z"
    return (
        f'<path d="{outer}" fill="{c["fur"]}" stroke="{c["shade"]}" stroke-width="6" stroke-linejoin="round"/>'
        f'<path d="{inside}" fill="{c["ear_in"]}"/><path d="{tip}" fill="{c["shade"]}" opacity="0.8"/>'
    )


def _face(c):
    brow = c.get("brow", c["shade"])
    whisker = c.get("whisker", c["shade"])
    mouth = c.get("mouth", c["eye"])
    eye_r = 27
    parts = [
        f'<path d="{_shaggy(256, 266, 152, 130, 30, 9, 24, seed=3)}" fill="{c["fur"]}" '
        f'stroke="{c["shade"]}" stroke-width="6" stroke-linejoin="round"/>',
        f'<path d="{_scallop(256, 150, 46, 26, 7, 10, start=180, end=360, closed=False)} Z" fill="{c["fur"]}"/>',
        f'<path d="{_shaggy(256, 338, 96, 62, 14, 6, 20, start=-15, end=195, seed=7)}" fill="{c["muzzle"]}"/>',
    ]
    for ex in (198, 314):
        brow_path = _scallop(ex, 222, 30, 12, 5, 7, start=180, end=360, closed=False)
        parts.append(f'<path d="{brow_path}" fill="none" stroke="{brow}" stroke-width="7" stroke-linecap="round"/>')
        rim = f' stroke="{c["eye_rim"]}" stroke-width="4"' if "eye_rim" in c else ""
        parts.append(f'<circle cx="{ex}" cy="258" r="{eye_r}" fill="{c["eye"]}"{rim}/>')
        parts.append(f'<circle cx="{ex - 8.6:.1f}" cy="248.3" r="8.6" fill="#fff"/>')
        parts.append(f'<circle cx="{ex + 9.4:.1f}" cy="267.4" r="3.8" fill="#fff"/>')
    parts.append(f'<ellipse cx="160" cy="310" rx="24" ry="13" fill="{c["ear_in"]}" opacity="0.65"/>')
    parts.append(f'<ellipse cx="352" cy="310" rx="24" ry="13" fill="{c["ear_in"]}" opacity="0.65"/>')
    nose_rim = f' stroke="{c["nose_rim"]}" stroke-width="4"' if "nose_rim" in c else ""
    nose = "M220,300 Q256,284 292,300 Q296,326 256,344 Q216,326 220,300 Z"
    parts.append(f'<path d="{nose}" fill="{c["nose"]}"{nose_rim}/>')
    parts.append('<ellipse cx="244" cy="302" rx="11" ry="6" fill="#fff" opacity="0.35"/>')
    parts.append(f'<path d="M240,368 Q256,394 272,368 Z" fill="{c["tongue"]}"/>')
    parts.append(
        '<path d="M256,344 V360 M256,360 Q240,374 224,364 M256,360 Q272,374 288,364" fill="none" '
        f'stroke="{mouth}" stroke-width="6" stroke-linecap="round"/>'
    )
    parts.append(
        '<path d="M190,352 L170,372 M206,366 L192,392 M322,352 L342,372 M306,366 L320,392" '
        f'stroke="{whisker}" stroke-width="5" stroke-linecap="round"/>'
    )
    return "".join(parts)


def dog_svg(variant: str) -> str:
    """SVG (512x512) del perrito con los colores de ``variant``."""
    c = {**BASE, **VARIANTS[variant]}
    body = _bandana(c) + _ear("l", c) + _ear("r", c) + _face(c)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">'
        f'<g transform="translate(0 -6)">{body}</g></svg>'
    )


def render(svg_text: str, size: int) -> Image.Image:
    with pymupdf.open(stream=svg_text.encode(), filetype="svg") as doc:
        page = doc[0]
        zoom = size / page.rect.width
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=True)
        return Image.frombytes("RGBA", (pixmap.width, pixmap.height), pixmap.samples)


def main() -> None:
    for variant in VARIANTS:
        stem = "app" if variant == "clasico" else f"app_{variant}"
        image = render(dog_svg(variant), 512)
        image.save(ICONS / f"{stem}.png", optimize=True)
        image.save(ICONS / f"{stem}.ico", sizes=ICO_SIZES)
        print("ok", stem)


if __name__ == "__main__":
    main()
