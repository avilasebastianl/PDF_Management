"""
Pestanas con icono para el panel lateral del visor.

Ocupan lo mismo en cualquier idioma (el nombre largo en ruso no cabria en un
selector de texto): cada pestana es un icono con su nombre en el tooltip, y el
nombre de la activa se muestra debajo.
"""

from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from .. import style
from ..icons import icon
from ..widgets import ToolTip


class IconTabs(ctk.CTkFrame):
    """``tabs``: ``(nombre, icono)``. ``set``/``get`` como ``CTkSegmentedButton`` (``set`` no avisa)."""

    def __init__(self, master, tabs: list[tuple[str, str]], command: Callable[[str], None]) -> None:
        super().__init__(master, fg_color="transparent")
        self.command = command
        self.names = [name for name, _icon in tabs]
        self._icons = dict(tabs)
        self._current = self.names[0]
        self.buttons: dict[str, ctk.CTkButton] = {}
        row = ctk.CTkFrame(self, fg_color=style.ROW_BG, corner_radius=8)
        row.pack(fill="x")
        for column, (name, icon_name) in enumerate(tabs):
            row.grid_columnconfigure(column, weight=1, uniform="tabs")
            button = ctk.CTkButton(
                row,
                text="" if icon(icon_name) else name[:3],
                image=icon(icon_name, 17, style.TEXT),
                height=30,
                width=36,
                corner_radius=6,
                fg_color="transparent",
                hover_color=style.HOVER,
                text_color=style.TEXT,
                command=lambda n=name: self._clicked(n),
            )
            button.grid(row=0, column=column, sticky="ew", padx=2, pady=2)
            ToolTip(button, name)
            self.buttons[name] = button
        self.title = ctk.CTkLabel(self, text="", font=style.fonts().body_bold, anchor="w")
        self.title.pack(fill="x", padx=4, pady=(6, 0))
        self.set(self._current)

    def cget(self, attribute: str):
        if attribute == "values":
            return list(self.names)
        return super().cget(attribute)

    def get(self) -> str:
        return self._current

    def set(self, name: str) -> None:
        self._current = name
        accent = style.accent_color()
        for tab, button in self.buttons.items():
            active = tab == name
            button.configure(
                fg_color=accent if active else "transparent",
                hover_color=style.accent_hover_color() if active else style.HOVER,
                image=icon(self._icons[tab], 17, style.WHITE if active else style.TEXT),
            )
        self.title.configure(text=name)

    def _clicked(self, name: str) -> None:
        self.set(name)
        self.command(name)
