# mypy: disable-error-code="misc"
# (self anotado como ViewerPage, su subclase: mypy lo marca, pero comprueba igual los atributos)
"""
Modos de lectura: visor en toda la ventana y pantalla completa.

Parte de ``ViewerPage`` (ver ``viewer.py``): los metodos anotan ``self`` con
``ViewerPage`` para que mypy compruebe los atributos que usan.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .. import style
from ..icons import icon

if TYPE_CHECKING:
    from .viewer import ViewerPage

NORMAL, WINDOW, FULLSCREEN = "normal", "ventana", "pantalla completa"


class ModesMixin:
    """Modos de lectura: visor en toda la ventana y pantalla completa."""

    @property
    def fullscreen(self: ViewerPage) -> bool:
        return self.view_mode == FULLSCREEN

    def toggle_fullscreen(self: ViewerPage) -> None:
        """Solo el visor en toda la pantalla (sin menu, barras, pestanas ni panel)."""
        self.set_view_mode(NORMAL if self.view_mode == FULLSCREEN else FULLSCREEN)

    def toggle_window_mode(self: ViewerPage) -> None:
        """El visor ocupa toda la ventana (con las pestanas), sin pasar a pantalla completa."""
        self.set_view_mode(NORMAL if self.view_mode == WINDOW else WINDOW)

    def set_view_mode(self: ViewerPage, mode: str) -> None:
        if mode == self.view_mode:
            return
        self.view_mode = mode
        reading = mode != NORMAL
        self.app.set_chrome_visible(not reading)
        if reading:
            self.file_bar.grid_remove()
            self.side.grid_remove()
        else:
            self.file_bar.grid()
            if self.side_visible:
                self.side.grid()
        if self.tabs and mode != FULLSCREEN:
            self.tab_bar.grid()
        else:
            self.tab_bar.grid_remove()
        self.app.root.attributes("-fullscreen", mode == FULLSCREEN)
        for button, name, active in (
            (self.window_button, "window_mode", mode == WINDOW),
            (self.fullscreen_button, "fullscreen", mode == FULLSCREEN),
        ):
            icon_name = f"exit_{name}" if active else name
            button.icon_key = icon_name
            button.configure(image=icon(icon_name, 16, style.TEXT))
        self.log("Modo de vista: %s", mode)

    def on_hide(self: ViewerPage) -> None:
        self.set_view_mode(NORMAL)
