"""
Segundo visor para comparar documentos lado a lado (vista dividida).

Muestra el documento de otra pestana, solo para leer. Con "Sincronizar" las
dos vistas pasan de pagina juntas.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk

from ...i18n import tr
from .. import style
from ..widgets import icon_button
from .page_view import PageView


class ComparePanel(ctk.CTkFrame):
    """Encabezado (documento, sincronizar, cerrar) y un ``PageView`` continuo."""

    def __init__(self, master, *, on_close: Callable[[], None]) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        header.grid_columnconfigure(0, weight=1)
        self.title = ctk.CTkLabel(header, text="", font=style.fonts().body_bold, anchor="w")
        self.title.grid(row=0, column=0, sticky="ew", padx=(4, 8))
        self.sync = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            header,
            text=tr("Sincronizar páginas"),
            variable=self.sync,
            font=style.fonts().small,
            checkbox_width=18,
            checkbox_height=18,
        ).grid(row=0, column=1, padx=(0, 6))
        icon_button(header, "clear", on_close, tr("Cerrar la comparación")).grid(row=0, column=2)
        self.view = PageView(self, continuous=True, placeholder=(tr("Elija un documento para comparar"), ""))
        self.view.grid(row=1, column=0, sticky="nsew")

    def set_title(self, name: str) -> None:
        self.title.configure(text=tr("Comparando con: {nombre}", nombre=name))
