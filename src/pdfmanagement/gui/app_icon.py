"""
Icono de la aplicacion: la variante de color del logo elegida en Ajustes se
aplica a la ventana, la barra de tareas, Alt+Tab y los dialogos que se abran.
"""

import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk

from .. import paths

_state = {"variant": "clasico"}
_photos: list[ImageTk.PhotoImage] = []  # Tk necesita que las imagenes sigan vivas


def current() -> str:
    """Variante aplicada ahora."""
    return _state["variant"]


def ico_path() -> Path:
    """``.ico`` de la variante actual (para los dialogos)."""
    return paths.app_icon_files(current())[0]


def logo_path() -> Path:
    """``.png`` de la variante actual (logo de la tarjeta "Acerca de")."""
    return paths.app_icon_files(current())[1]


def apply(root: tk.Tk, variant: str) -> None:
    """Cambia el icono de la ventana principal y de las ventanas ya abiertas."""
    _state["variant"] = variant if variant in paths.APP_ICON_VARIANTS else "clasico"
    ico, png = paths.app_icon_files(current())
    if ico.exists():
        root.iconbitmap(default=str(ico))  # default: tambien los dialogos nuevos
        for child in root.winfo_children():
            if isinstance(child, tk.Toplevel):
                child.iconbitmap(str(ico))
    if png.exists():
        with Image.open(png) as source:
            image = source.convert("RGBA")
        # Un solo PNG de 64 px (el .ico ya trae los demas tamanos). Pasar varios tamanos a
        # iconphoto, incluido 256, desordena la pantalla completa y el modo ventana del Visor.
        photo = ImageTk.PhotoImage(image.resize((64, 64), Image.Resampling.LANCZOS), master=root)
        root.iconphoto(True, str(photo))
        _photos[:] = [photo]
