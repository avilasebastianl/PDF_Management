"""
Tokens visuales compartidos: tipografia, espaciado y colores semanticos.

Los colores se expresan como tuplas ``(modo claro, modo oscuro)``, el formato
que CustomTkinter usa para cambiar de tema en caliente.
"""

from dataclasses import dataclass
from functools import cache

import customtkinter as ctk

FONT_FAMILY = "Segoe UI"

# * Espaciado
PAD = 20          # margen externo de las paginas
CARD_PAD = 16     # margen interno de las tarjetas
GAP = 10          # separacion entre elementos
SIDEBAR_WIDTH = 220
CORNER = 10

# * Colores semanticos
TEXT = ("gray10", "gray92")
TEXT_MUTED = ("gray40", "gray62")
TEXT_DISABLED = ("gray75", "gray35")
SIDEBAR_BG = ("gray88", "gray12")
CONTENT_BG = ("gray95", "gray16")
CARD_BG = ("white", "gray20")
CARD_BORDER = ("gray85", "gray26")
HOVER = ("gray82", "gray28")
ROW_BG = ("gray96", "gray24")
SUCCESS = ("#2E7D32", "#66BB6A")
DANGER = ("#C62828", "#EF5350")
WARNING = ("#B26A00", "#FFB74D")
CANVAS_BG = ("#D9D9DE", "#1B1B1F")
PAGE_SHADOW = ("#B4B4BA", "#0B0B0D")
WHITE = ("white", "white")


@dataclass(frozen=True)
class Fonts:
    title: ctk.CTkFont
    subtitle: ctk.CTkFont
    section: ctk.CTkFont
    body: ctk.CTkFont
    body_bold: ctk.CTkFont
    small: ctk.CTkFont
    brand: ctk.CTkFont


@cache
def fonts() -> Fonts:
    """Fuentes de la aplicacion. Debe llamarse despues de crear la ventana raiz."""
    return Fonts(
        title=ctk.CTkFont(FONT_FAMILY, 24, "bold"),
        subtitle=ctk.CTkFont(FONT_FAMILY, 13),
        section=ctk.CTkFont(FONT_FAMILY, 15, "bold"),
        body=ctk.CTkFont(FONT_FAMILY, 13),
        body_bold=ctk.CTkFont(FONT_FAMILY, 13, "bold"),
        small=ctk.CTkFont(FONT_FAMILY, 11),
        brand=ctk.CTkFont(FONT_FAMILY, 17, "bold"),
    )


def accent_color() -> tuple[str, str]:
    """Color principal del tema activo (el de los botones)."""
    color = ctk.ThemeManager.theme["CTkButton"]["fg_color"]
    return tuple(color) if isinstance(color, list) else (color, color)


def accent_hover_color() -> tuple[str, str]:
    color = ctk.ThemeManager.theme["CTkButton"]["hover_color"]
    return tuple(color) if isinstance(color, list) else (color, color)


def themed(color: tuple[str, str]) -> str:
    """Resuelve una tupla de color segun el modo de apariencia actual."""
    return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]
