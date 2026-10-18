r"""
Genera las variantes de color del logo (``assets/icons/app_<variante>.png`` y
``.ico``) a partir de ``assets/icons/app.png``, el original ("Clasico").

Recolorea solo la cara (amarillo) y las orejas (marron) cambiando el tono; el
contorno negro, los ojos, la nariz y la barba quedan iguales. Uso::

    venv\Scripts\python.exe tools\make_icon_variants.py
"""

from pathlib import Path

import numpy as np
from PIL import Image

ICONS = Path(__file__).resolve().parents[1] / "assets" / "icons"
ICO_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

# variante -> ((tono cara, saturacion x, brillo x), (tono orejas, saturacion x, brillo x)); tono en grados.
VARIANTS = {
    "azul": ((205, 1.0, 1.0), (220, 1.0, 0.95)),
    "verde": ((125, 0.65, 0.88), (150, 0.9, 0.8)),
    "rosa": ((335, 0.75, 1.05), (300, 0.8, 1.0)),
    "morado": ((270, 0.8, 1.0), (250, 0.9, 0.9)),
    "plata": ((210, 0.12, 0.95), (215, 0.15, 0.8)),
}


def recolor(image: Image.Image, face: tuple[float, float, float], ears: tuple[float, float, float]) -> Image.Image:
    rgba = np.asarray(image.convert("RGBA")).astype(np.float64) / 255
    rgb, alpha = rgba[..., :3], rgba[..., 3:]
    high, low = rgb.max(axis=-1), rgb.min(axis=-1)
    delta = high - low
    saturation = np.where(high > 0, delta / np.maximum(high, 1e-9), 0)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    safe = np.maximum(delta, 1e-9)
    hue = np.select(
        [high == r, high == g], [((g - b) / safe) % 6, (b - r) / safe + 2], (r - g) / safe + 4
    ) * 60  # fmt: skip
    colored = (saturation > 0.18) & (high > 0.12)  # sin contorno negro ni grises (ojos, nariz)
    is_face = colored & (hue >= 36) & (hue <= 75)
    is_ears = colored & ((hue < 36) | (hue > 330))
    new_h, new_s, new_v = hue.copy(), saturation.copy(), high.copy()
    for mask, (target, s_mul, v_mul) in ((is_face, face), (is_ears, ears)):
        new_h[mask] = target
        new_s[mask] = np.clip(saturation[mask] * s_mul, 0, 1)
        new_v[mask] = np.clip(high[mask] * v_mul, 0, 1)
    # HSV -> RGB
    sector = (new_h / 60) % 6
    chroma = new_v * new_s
    x = chroma * (1 - np.abs(sector % 2 - 1))
    zero = np.zeros_like(chroma)
    index = np.floor(sector).astype(int)
    options = [
        (chroma, x, zero), (x, chroma, zero), (zero, chroma, x),
        (zero, x, chroma), (x, zero, chroma), (chroma, zero, x),
    ]  # fmt: skip
    out = np.zeros_like(rgb)
    for i, (rr, gg, bb) in enumerate(options):
        sel = index == i
        out[..., 0][sel], out[..., 1][sel], out[..., 2][sel] = rr[sel], gg[sel], bb[sel]
    out += (new_v - chroma)[..., None]
    changed = (is_face | is_ears)[..., None]
    result = np.where(changed, out, rgb)
    return Image.fromarray((np.concatenate([result, alpha], axis=-1) * 255).round().astype(np.uint8), "RGBA")


def main() -> None:
    original = Image.open(ICONS / "app.png").convert("RGBA")
    for name, (face, ears) in VARIANTS.items():
        image = recolor(original, face, ears)
        image.save(ICONS / f"app_{name}.png", optimize=True)
        image.save(ICONS / f"app_{name}.ico", sizes=ICO_SIZES)
        print("ok", name)


if __name__ == "__main__":
    main()
