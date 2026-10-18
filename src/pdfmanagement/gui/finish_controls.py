"""
Controles compartidos: opciones de marca de agua y vista previa de una pagina.

Los usan Herramientas y Unir, asi la marca de agua se ve y se comporta igual
en las dos secciones.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk
from PIL import Image

from ..core.finish import WatermarkOptions
from ..i18n import tr
from . import style
from .widgets import field_label, set_label_image

# Orientacion de la marca de agua -> angulo (grados, antihorario como se ve).
ORIENTATIONS = {tr("Diagonal"): 45, tr("Horizontal"): 0, tr("Vertical"): 90, tr("Diagonal inversa"): -45}


LABEL_WIDTH = 96  # columna de etiquetas igual en todos los grupos (quedan alineadas)


def _grid_row(parent, row: int, label: str, widget, **options) -> None:
    parent.grid_columnconfigure(0, minsize=LABEL_WIDTH)
    field_label(parent, label).grid(row=row, column=0, sticky="w", padx=(0, style.GAP), pady=6)
    widget.grid(row=row, column=1, sticky=options.pop("sticky", "w"), pady=6, **options)


class WatermarkControls(ctk.CTkFrame):
    """Texto, opacidad, orientacion y si va detras del contenido."""

    def __init__(self, master, on_change: Callable[[], None] | None = None) -> None:
        super().__init__(master, fg_color="transparent")
        self.on_change = on_change or (lambda: None)
        self.grid_columnconfigure(1, weight=1)
        self.mark_text = tk.StringVar(value=tr("CONFIDENCIAL"))
        self.mark_text.trace_add("write", lambda *_: self.on_change())
        _grid_row(self, 0, tr("Texto"), ctk.CTkEntry(self, textvariable=self.mark_text, width=260, height=34))
        self.opacity = ctk.CTkSlider(
            self, from_=5, to=60, number_of_steps=11, width=240, command=lambda _v: self.on_change()
        )
        self.opacity.set(15)
        _grid_row(self, 1, tr("Opacidad"), self.opacity)
        self.orientation = ctk.CTkSegmentedButton(
            self, values=list(ORIENTATIONS), command=lambda _v: self.on_change(), font=style.fonts().small
        )
        self.orientation.set(next(iter(ORIENTATIONS)))
        _grid_row(self, 2, tr("Orientación"), self.orientation)
        self.behind = ctk.CTkSwitch(
            self, text=tr("Detrás del contenido"), font=style.fonts().body, command=lambda: self.on_change()
        )
        _grid_row(self, 3, "", self.behind)

    @property
    def angle(self) -> float:
        return ORIENTATIONS.get(self.orientation.get(), 45)

    def options(self) -> WatermarkOptions:
        return WatermarkOptions(
            self.mark_text.get(), opacity=self.opacity.get() / 100, angle=self.angle, behind=bool(self.behind.get())
        )


class PreviewPane(ctk.CTkLabel):
    """Vista previa de una pagina (imagen con un borde fino) o un mensaje cuando no hay."""

    def __init__(self, master, height: int, message: str) -> None:
        self.box = (round(height * 0.72), height)
        super().__init__(
            master,
            text=message,
            width=self.box[0],
            height=self.box[1],
            fg_color=style.CANVAS_BG,
            corner_radius=8,
            text_color=style.TEXT_MUTED,
            font=style.fonts().small,
            wraplength=round(height * 0.6),
        )
        self.preview_height = height
        self.image: ctk.CTkImage | None = None

    @property
    def pixel_height(self) -> int:
        return round(self.preview_height * ctk.ScalingTracker.get_widget_scaling(self))

    def set_image(self, image: Image.Image) -> None:
        bordered = Image.new("RGB", (image.width + 2, image.height + 2), (190, 194, 202))  # borde de la hoja
        bordered.paste(image, (1, 1))
        scaling = ctk.ScalingTracker.get_widget_scaling(self)
        size = (round(bordered.width / scaling), round(bordered.height / scaling))
        image_ctk = ctk.CTkImage(light_image=bordered, dark_image=bordered, size=size)
        # Primero se suelta la imagen anterior del widget Tk y despues se libera (ver set_label_image).
        set_label_image(self, image_ctk)
        self.configure(width=size[0], height=size[1], fg_color="transparent")
        self.image = image_ctk

    def set_message(self, text: str) -> None:
        set_label_image(self, None, text)
        self.configure(width=self.box[0], height=self.box[1], fg_color=style.CANVAS_BG)
        self.image = None  # recien ahora: el widget ya no la usa
