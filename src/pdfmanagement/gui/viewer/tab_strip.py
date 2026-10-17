"""
Barra de pestanas de documentos, con aspecto de navegador.

Pestanas del mismo ancho que se encogen cuando hay muchas, icono de PDF,
titulo recortado, punto de "cambios sin guardar", boton de cerrar visible en
la pestana activa o al pasar el cursor, clic central para cerrar y una barra
de acento bajo la pestana activa.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import customtkinter as ctk

from .. import style
from ..icons import icon
from ..widgets import ToolTip, icon_button

TAB_MAX_WIDTH = 210
TAB_MIN_WIDTH = 120
TAB_HEIGHT = 34
NEW_BUTTON_SPACE = 44
CHAR_WIDTH = 7.2  # ancho medio de un caracter de la fuente de las pestanas (para recortar titulos)


@dataclass(frozen=True)
class TabInfo:
    title: str
    tooltip: str
    modified: bool = False


class TabStrip(ctk.CTkFrame):
    def __init__(
        self, master, *, on_select: Callable[[int], None], on_close: Callable[[int], None], on_new: Callable[[], None]
    ) -> None:
        super().__init__(master, fg_color="transparent", height=TAB_HEIGHT + 4)
        self.on_select = on_select
        self.on_close = on_close
        self.on_new = on_new
        self.tabs: list[TabInfo] = []
        self.active = -1
        self._widgets: list[dict] = []
        self._width = TAB_MAX_WIDTH
        self.bind("<Configure>", self._on_resize)

    # * API -----------------------------------------------------------------

    def set_tabs(self, tabs: list[TabInfo], active: int) -> None:
        self.tabs, self.active = list(tabs), active
        self._render()

    def update_tab(self, index: int, info: TabInfo) -> None:
        """Actualiza titulo y punto de cambios de una pestana sin redibujar la barra."""
        if not 0 <= index < len(self._widgets):
            return
        self.tabs[index] = info
        parts = self._widgets[index]
        title = self._fit(info.title)
        if parts["title"].cget("text") != title:
            parts["title"].configure(text=title)
        self._refresh_close(index)

    def titles(self) -> list[str]:
        return [parts["title"].cget("text") for parts in self._widgets]

    # * Dibujo --------------------------------------------------------------

    def _tab_width(self) -> int:
        available = max(self.winfo_width(), 400) - NEW_BUTTON_SPACE
        return int(max(TAB_MIN_WIDTH, min(TAB_MAX_WIDTH, available / max(len(self.tabs), 1) - 4)))

    def _fit(self, title: str) -> str:
        room = int((self._width - 74) / CHAR_WIDTH)  # icono, margenes y boton de cerrar
        return title if len(title) <= room else title[: max(room - 1, 4)] + "…"

    def _render(self) -> None:
        for widget in self.winfo_children():
            widget.destroy()
        self._widgets = []
        self._width = self._tab_width()
        accent = style.accent_color()
        for index, info in enumerate(self.tabs):
            active = index == self.active
            tab = ctk.CTkFrame(
                self,
                width=self._width,
                height=TAB_HEIGHT,
                corner_radius=8,
                fg_color=style.CARD_BG if active else "transparent",
                border_width=1 if active else 0,
                border_color=style.CARD_BORDER,
            )
            tab.pack(side="left", padx=(0, 4), pady=(2, 2))
            tab.pack_propagate(False)
            tab.grid_propagate(False)
            glyph = ctk.CTkLabel(tab, text="", width=18, image=icon("pdf", 16, accent if active else style.TEXT_MUTED))
            glyph.place(x=10, rely=0.5, anchor="w")
            title = ctk.CTkLabel(
                tab,
                text=self._fit(info.title),
                anchor="w",
                font=style.fonts().body_bold if active else style.fonts().body,
                text_color=style.TEXT if active else style.TEXT_MUTED,
            )
            title.place(x=34, rely=0.5, anchor="w")
            dot = ctk.CTkLabel(tab, text="●", width=20, font=style.fonts().small, text_color=accent)
            close = icon_button(tab, "clear", lambda i=index: self.on_close(i), "Cerrar pestana (Ctrl+W)", size=22)
            indicator = ctk.CTkFrame(tab, height=3, corner_radius=2, fg_color=accent if active else "transparent")
            indicator.place(relx=0.5, rely=1.0, y=-3, anchor="s", relwidth=0.86)
            parts = {"frame": tab, "title": title, "dot": dot, "close": close, "hover": False}
            self._widgets.append(parts)
            for widget in (tab, glyph, title, dot):
                widget.bind("<Button-1>", lambda _e, i=index: self.on_select(i))
                widget.bind("<Button-2>", lambda _e, i=index: self.on_close(i))
                widget.bind("<Enter>", lambda _e, i=index: self._hover(i, True), add="+")
                widget.bind("<Leave>", lambda _e, i=index: self._hover(i, False), add="+")
            close.bind("<Enter>", lambda _e, i=index: self._hover(i, True), add="+")
            ToolTip(title, info.tooltip)
            self._refresh_close(index)
        new = icon_button(self, "add", self.on_new, "Abrir otro PDF en una pestana nueva (Ctrl+O)", size=30)
        new.pack(side="left", padx=(2, 0))

    def _hover(self, index: int, inside: bool) -> None:
        if index >= len(self._widgets):
            return
        parts = self._widgets[index]
        parts["hover"] = inside
        if index != self.active:
            wanted = style.HOVER if inside else "transparent"
            if parts["frame"].cget("fg_color") != wanted:
                parts["frame"].configure(fg_color=wanted)
        self._refresh_close(index)

    def _refresh_close(self, index: int) -> None:
        """La X se ve en la activa o al pasar el cursor; si no, el punto de cambios sin guardar."""
        parts = self._widgets[index]
        show_close = index == self.active or parts["hover"]
        modified = self.tabs[index].modified
        if show_close:
            parts["dot"].place_forget()
            parts["close"].place(relx=1.0, x=-6, rely=0.5, anchor="e")
            if modified and index == self.active:
                parts["dot"].place(relx=1.0, x=-30, rely=0.5, anchor="e")
        else:
            parts["close"].place_forget()
            if modified:
                parts["dot"].place(relx=1.0, x=-8, rely=0.5, anchor="e")
            else:
                parts["dot"].place_forget()

    def _on_resize(self, _event=None) -> None:
        if self.tabs and abs(self._tab_width() - self._width) > 6:
            self._render()
