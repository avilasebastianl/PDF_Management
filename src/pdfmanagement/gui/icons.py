"""
Iconos vectoriales generados a partir de la fuente de iconos de Windows
(Segoe Fluent Icons / Segoe MDL2 Assets).

Se renderizan en tiempo de ejecucion en dos colores (modo claro y oscuro), asi
que no hay imagenes que mantener y siempre se ven nitidos con cualquier escala.
Si la fuente no existe, los botones se muestran solo con texto.
"""

import logging
import os
from functools import cache
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageColor, ImageDraw, ImageFont

from . import style

logger = logging.getLogger(__name__)

GLYPHS = {
    "merge": "\ue8c8",
    "extract": "\ue8c6",
    "convert": "\ue8ab",
    "sign": "\uee56",
    "protect": "\uea18",
    "settings": "\ue713",
    "help": "\ue897",
    "add": "\ue710",
    "minus": "\ue738",
    "delete": "\ue74d",
    "up": "\ue70e",
    "down": "\ue70d",
    "previous": "\ue76b",
    "next": "\ue76c",
    "first": "\ue892",
    "last": "\ue893",
    "zoom_in": "\ue8a3",
    "zoom_out": "\ue71f",
    "fit": "\ue9a6",
    "folder": "\ue8b7",
    "open": "\ue8e5",
    "moon": "\ue708",
    "sun": "\ue706",
    "clear": "\ue894",
    "check": "\ue73e",
    "info": "\ue946",
    "pdf": "\uea90",
    "edit": "\ue70f",
    "image": "\ueb9f",
    "lock": "\ue72e",
    "unlock": "\ue785",
    "sort": "\ue8cb",
    "eye": "\ue890",
    "heart": "\ueb51",
    "refresh": "\ue72c",
    "list": "\ue8fd",
    "menu": "\ue700",
    "tools": "\ue90f",
    "fullscreen": "\ue740",
    "exit_fullscreen": "\ue73f",
    "window_mode": "\ue737",
    "exit_window_mode": "\uee49",
    "search": "\ue721",
    "highlight": "\ue7e6",
    "underline": "\ue8dc",
    "strikeout": "\uede0",
    "note": "\ue90a",
    "free_text": "\ue8d2",
    "rectangle": "\ue739",
    "ellipse": "\uea3a",
    "line": "\ue738",
    "arrow": "\ue72a",
    "ink": "\uedc6",
    "save_as": "\ue792",
    "undo": "\ue7a7",
    "redo": "\ue7a6",
    "rotate_right": "\ue8b4",
    "rotate_left": "\ue8b4",  # reflejado (ver MIRRORED)
    "insert_pdf": "\ued0e",
    "blank_page": "\ue7c3",
    "replace_text": "\ue8ac",
    "fixed_text": "\ue8e9",
    "redact": "\ued1a",
    "print": "\ue749",
    "night": "\ue708",
    "two_pages": "\ue89a",
    "compare": "\ueb91",
    "pages_tab": "\ue8a9",
    "outline": "\ue8a4",
    "signature": "\uee56",
    "view_options": "\ue890",
}

# La fuente no trae algunas variantes; se obtienen reflejando horizontalmente.
MIRRORED = {"rotate_left"}

_FONT_CANDIDATES = ("SegoeIcons.ttf", "segmdl2.ttf")


@cache
def _font_path() -> Path | None:
    fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    for name in _FONT_CANDIDATES:
        candidate = fonts_dir / name
        if candidate.exists():
            return candidate
    logger.warning("No se encontro la fuente de iconos de Windows; se usaran botones de texto.")
    return None


def _to_rgb(color: str) -> tuple[int, int, int]:
    """Convierte colores de PIL y los grises de Tk (``gray0``-``gray100``)."""
    name = color.lower()
    for prefix in ("gray", "grey"):
        if name.startswith(prefix) and name[len(prefix) :].isdigit():
            level = round(int(name[len(prefix) :]) * 2.55)
            return level, level, level
    return ImageColor.getrgb(color)[:3]


@cache
def _render(glyph: str, size: int, color: str, mirrored: bool = False) -> Image.Image:
    font_path = _font_path()
    scale = 3  # renderizado a mayor resolucion para que se vea nitido al escalar
    pixels = size * scale
    image = Image.new("RGBA", (pixels, pixels), (0, 0, 0, 0))
    font = ImageFont.truetype(str(font_path), int(pixels * 0.82))
    ImageDraw.Draw(image).text((pixels / 2, pixels / 2), glyph, font=font, fill=_to_rgb(color), anchor="mm")
    return image.transpose(Image.Transpose.FLIP_LEFT_RIGHT) if mirrored else image


def render_glyph(glyph: str, size: int, color: str) -> Image.Image | None:
    """
    Icono como imagen PIL en un solo color (para dibujar en un ``Canvas``).
    Devuelve ``None`` si la fuente de iconos no esta disponible.
    """
    if _font_path() is None:
        return None
    return _render(glyph, size, color)


@cache
def icon(name: str, size: int = 18, color: tuple[str, str] = style.TEXT) -> ctk.CTkImage | None:
    """
    Devuelve el icono ``name`` como ``CTkImage`` adaptable al tema.

    Args:
        name: Clave de ``GLYPHS``.
        size: Lado en pixeles logicos.
        color: Colores ``(claro, oscuro)`` del trazo.
    """
    if _font_path() is None:
        return None
    glyph = GLYPHS[name]
    mirrored = name in MIRRORED
    light, dark = color
    return ctk.CTkImage(
        light_image=_render(glyph, size, light, mirrored),
        dark_image=_render(glyph, size, dark, mirrored),
        size=(size, size),
    )
