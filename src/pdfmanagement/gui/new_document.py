"""
Dialogo "Nuevo PDF": elegir plantilla (con vista previa), tamano de papel,
orientacion y numero de paginas.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk
import pymupdf
from PIL import Image

from ..core.create import MAX_PAGES, MULTI_PAGE, TEMPLATES, NewDocument, build_document, size_names, template_names
from ..i18n import tr
from . import style
from .dialogs import _prepare_toplevel
from .dropdown import dropdown_menu
from .widgets import field_label, muted_label, primary_button, secondary_button, set_label_image

PREVIEW_HEIGHT = 128
ORIENTATIONS = (tr("Vertical"), tr("Horizontal"))


class NewDocumentDialog(ctk.CTkToplevel):
    """Modal; ``result`` queda con lo elegido o ``None`` si se cancela."""

    def __init__(self, parent) -> None:
        super().__init__(parent.winfo_toplevel())
        _prepare_toplevel(self, parent, tr("Nuevo PDF"), 700, 600, modal=True)
        self.resizable(False, False)
        self.result: NewDocument | None = None
        self.template = "blank"
        self._names = template_names()
        self._sizes = {name: key for key, name in size_names().items()}
        self._previews: dict[str, ctk.CTkImage] = {}
        self.cards: dict[str, ctk.CTkFrame] = {}
        self._images: dict[str, ctk.CTkLabel] = {}

        ctk.CTkLabel(self, text=tr("Nuevo PDF"), font=style.fonts().section, anchor="w").pack(
            fill="x", padx=24, pady=(20, 0)
        )
        muted_label(
            self,
            tr("Elija una plantilla. Se abre en una pestaña nueva del Visor; guárdelo con «Guardar como»."),
            anchor="w",
            justify="left",
            wraplength=640,
        ).pack(fill="x", padx=24, pady=(2, 12))

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.pack(fill="x", padx=18)
        for column in range(3):
            grid.grid_columnconfigure(column, weight=1, uniform="cards")
        for index, key in enumerate(TEMPLATES):
            self._add_card(grid, index, key)

        options = ctk.CTkFrame(self, fg_color="transparent")
        options.pack(fill="x", padx=24, pady=(14, 0))
        field_label(options, tr("Tamaño")).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.size_menu = dropdown_menu(options, list(self._sizes), lambda _v: self._refresh_previews(), width=150)
        self.size_menu.set(size_names()["A4"])
        self.size_menu.grid(row=0, column=1, padx=(0, 20))
        field_label(options, tr("Orientación")).grid(row=0, column=2, sticky="w", padx=(0, 8))
        self.orientation = ctk.CTkSegmentedButton(
            options, values=list(ORIENTATIONS), command=lambda _v: self._refresh_previews(), font=style.fonts().small
        )
        self.orientation.set(ORIENTATIONS[0])
        self.orientation.grid(row=0, column=3, padx=(0, 20))
        field_label(options, tr("Páginas")).grid(row=0, column=4, sticky="w", padx=(0, 8))
        self.pages = tk.StringVar(value="1")
        self.pages_entry = ctk.CTkEntry(options, textvariable=self.pages, width=60, justify="center")
        self.pages_entry.grid(row=0, column=5)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(side="bottom", fill="x", padx=24, pady=(0, 20))
        primary_button(buttons, tr("Crear"), self._accept, "add", width=130).pack(side="right")
        secondary_button(buttons, tr("Cancelar"), self.destroy, width=110).pack(side="right", padx=(0, 8))
        self.error = ctk.CTkLabel(buttons, text="", text_color=style.DANGER, font=style.fonts().small, anchor="w")
        self.error.pack(side="left", fill="x", expand=True)

        self.bind("<Return>", lambda _e: self._accept())
        self._refresh_previews()
        self.select(self.template)
        self.after(60, self.focus_force)

    # * Tarjetas --------------------------------------------------------------------

    def _add_card(self, grid, index: int, key: str) -> None:
        card = ctk.CTkFrame(
            grid, corner_radius=10, border_width=2, border_color=style.CARD_BORDER, fg_color=style.CARD_BG
        )
        card.grid(row=index // 3, column=index % 3, sticky="nsew", padx=6, pady=6)
        image = ctk.CTkLabel(card, text="", height=PREVIEW_HEIGHT + 8)
        image.pack(padx=10, pady=(10, 4))
        name = ctk.CTkLabel(card, text=self._names[key], font=style.fonts().body_bold)
        name.pack(pady=(0, 10))
        for widget in (card, image, name):
            widget.bind("<Button-1>", lambda _e, k=key: self.select(k))
            widget.bind("<Double-Button-1>", lambda _e, k=key: self._choose_and_accept(k))
            widget.configure(cursor="hand2")
        self.cards[key] = card
        self._images[key] = image

    def _choose_and_accept(self, key: str) -> None:
        self.select(key)
        self._accept()

    def select(self, key: str) -> None:
        self.template = key
        accent = style.accent_color()
        for name, card in self.cards.items():
            card.configure(border_color=accent if name == key else style.CARD_BORDER)
        multi = key in MULTI_PAGE
        self.pages_entry.configure(state="normal" if multi else "disabled")
        if not multi:
            self.pages.set("1")
        self.error.configure(text="")

    def _refresh_previews(self) -> None:
        for key in TEMPLATES:
            preview = self._render(key)
            set_label_image(self._images[key], preview)  # suelta la anterior antes de liberarla
            self._previews[key] = preview

    def _render(self, key: str) -> ctk.CTkImage:
        spec = NewDocument(key, self._size_key(), self._landscape(), 1)
        document = build_document(spec)
        try:
            page = document[0]
            scaling = ctk.ScalingTracker.get_widget_scaling(self)
            zoom = PREVIEW_HEIGHT * scaling * 2 / page.rect.height  # doble resolucion: nitido
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        finally:
            document.close()
        width = round(PREVIEW_HEIGHT * image.width / image.height)
        bordered = Image.new("RGB", (image.width + 2, image.height + 2), (190, 194, 202))
        bordered.paste(image, (1, 1))
        return ctk.CTkImage(light_image=bordered, dark_image=bordered, size=(width, PREVIEW_HEIGHT))

    # * Resultado ---------------------------------------------------------------------

    def _size_key(self) -> str:
        return self._sizes.get(self.size_menu.get(), "A4")

    def _landscape(self) -> bool:
        return self.orientation.get() == ORIENTATIONS[1]

    def _accept(self) -> None:
        try:
            pages = int(self.pages.get())
        except ValueError:
            pages = 0
        if not 1 <= pages <= MAX_PAGES:
            self.error.configure(text=tr("El número de páginas debe estar entre 1 y {maximo}.", maximo=MAX_PAGES))
            return
        self.result = NewDocument(self.template, self._size_key(), self._landscape(), pages)
        self.destroy()


def ask_new_document(parent) -> NewDocument | None:
    """Muestra el dialogo y espera; devuelve lo elegido o ``None``."""
    dialog = NewDocumentDialog(parent)
    dialog.wait_window()
    return dialog.result
