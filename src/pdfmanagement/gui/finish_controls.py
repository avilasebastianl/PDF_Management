"""
Controles compartidos para terminar un PDF: marca de agua, firma y vista previa.

Los usan Herramientas (marca de agua) y Unir (marca de agua y firma), asi las
opciones se ven y se comportan igual en todas las secciones.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

from .. import signatures
from ..core import InvalidInputError
from ..core.finish import SignatureOptions, WatermarkOptions
from ..i18n import tr
from . import style
from .dropdown import dropdown_menu, set_dropdown_values
from .widgets import field_label, muted_label, secondary_button, set_label_image

# Orientacion de la marca de agua -> angulo (grados, antihorario como se ve).
ORIENTATIONS = {tr("Diagonal"): 45, tr("Horizontal"): 0, tr("Vertical"): 90, tr("Diagonal inversa"): -45}
SIGNATURE_KINDS = {tr("Firma visual"): "visual", tr("Firma digital"): "digital"}
POSITIONS = {
    tr("Abajo a la derecha"): "abajo-derecha",
    tr("Abajo al centro"): "abajo-centro",
    tr("Abajo a la izquierda"): "abajo-izquierda",
    tr("Arriba a la derecha"): "arriba-derecha",
    tr("Arriba a la izquierda"): "arriba-izquierda",
}
SIGNATURE_PAGES = {tr("Última"): "ultima", tr("Primera"): "primera", tr("Todas"): "todas"}
NO_SIGNATURES = tr("(sin firmas guardadas)")
CERTIFICATE_TYPES = ((tr("Certificados digitales"), "*.pfx *.p12"),)


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


class SignatureControls(ctk.CTkFrame):
    """Firma visual (de la biblioteca de firmas) o digital (certificado), con posicion y tamano."""

    def __init__(self, master, on_change: Callable[[], None] | None = None) -> None:
        super().__init__(master, fg_color="transparent")
        self.on_change = on_change or (lambda: None)
        self.grid_columnconfigure(1, weight=1)
        self.kind = ctk.CTkSegmentedButton(
            self, values=list(SIGNATURE_KINDS), command=self._on_kind, font=style.fonts().small
        )
        self.kind.set(next(iter(SIGNATURE_KINDS)))
        _grid_row(self, 0, tr("Tipo"), self.kind)

        # Firma visual: una imagen de la biblioteca (la misma de la seccion Firmar).
        self.visual = ctk.CTkFrame(self, fg_color="transparent")
        self.visual.grid_columnconfigure(1, weight=1)
        self.library = dropdown_menu(self.visual, [NO_SIGNATURES], lambda _v: self.on_change(), width=240)
        _grid_row(self.visual, 0, tr("Firma"), self.library)
        self.library_hint = muted_label(self.visual, tr("Las firmas se guardan en la sección Firmar."))
        self.library_hint.grid(row=1, column=1, sticky="w")

        # Firma digital: certificado y su contrasena.
        self.digital = ctk.CTkFrame(self, fg_color="transparent")
        self.digital.grid_columnconfigure(1, weight=1)
        certificate_row = ctk.CTkFrame(self.digital, fg_color="transparent")
        self.certificate = tk.StringVar()
        ctk.CTkEntry(certificate_row, textvariable=self.certificate, width=260, height=34).pack(side="left")
        secondary_button(certificate_row, tr("Examinar"), self._browse_certificate, "folder", width=110).pack(
            side="left", padx=(8, 0)
        )
        _grid_row(self.digital, 0, tr("Certificado"), certificate_row)
        self.certificate_password = tk.StringVar()
        _grid_row(
            self.digital,
            1,
            tr("Contraseña"),
            ctk.CTkEntry(self.digital, textvariable=self.certificate_password, show="•", width=260, height=34),
        )

        self.position = dropdown_menu(self, list(POSITIONS), lambda _v: self.on_change(), width=240)
        _grid_row(self, 2, tr("Posición"), self.position)
        self.pages = ctk.CTkSegmentedButton(
            self, values=list(SIGNATURE_PAGES), command=lambda _v: self.on_change(), font=style.fonts().small
        )
        self.pages.set(next(iter(SIGNATURE_PAGES)))
        _grid_row(self, 3, tr("Página"), self.pages)
        self.width = ctk.CTkSlider(
            self, from_=80, to=260, number_of_steps=18, width=240, command=lambda _v: self.on_change()
        )
        self.width.set(150)
        _grid_row(self, 4, tr("Tamaño"), self.width)
        self.reload_library()
        self._on_kind(self.kind.get(), notify=False)

    def reload_library(self) -> None:
        """Vuelve a leer las firmas guardadas (pueden agregarse en Firmar)."""
        self._library = {path.stem: path for path in signatures.list_signatures()}
        names = list(self._library) or [NO_SIGNATURES]
        set_dropdown_values(self.library, names)
        if self.library.get() not in names:
            self.library.set(names[0])

    def _on_kind(self, label: str, notify: bool = True) -> None:
        visual = SIGNATURE_KINDS.get(label) == "visual"
        (self.digital if visual else self.visual).grid_remove()
        (self.visual if visual else self.digital).grid(row=1, column=0, columnspan=2, sticky="ew")
        if notify:
            self.on_change()

    def _browse_certificate(self) -> None:
        chosen = filedialog.askopenfilename(title=tr("Certificado digital"), filetypes=CERTIFICATE_TYPES)
        if chosen:
            self.certificate.set(chosen)
            self.on_change()

    def options(self, *, for_preview: bool = False) -> SignatureOptions:
        """Opciones elegidas. Sin ``for_preview`` valida que esten la imagen o el certificado."""
        kind = SIGNATURE_KINDS.get(self.kind.get(), "visual")
        pages = SIGNATURE_PAGES.get(self.pages.get(), "ultima")
        common = {
            "position": POSITIONS.get(self.position.get(), "abajo-derecha"),
            "pages": "ultima" if kind == "digital" and pages == "todas" else pages,
            "width": float(self.width.get()),
        }
        if kind == "visual":
            image = self._library.get(self.library.get())
            if image is None and not for_preview:
                raise InvalidInputError(tr("Guarde una firma en la sección Firmar para poder usarla aquí."))
            return SignatureOptions("visual", image=image, **common)  # type: ignore[arg-type]
        certificate = self.certificate.get().strip()
        if not certificate and not for_preview:
            raise InvalidInputError(tr("Elija el certificado digital (.pfx o .p12)."))
        return SignatureOptions(
            "digital",
            certificate=Path(certificate) if certificate else None,
            certificate_password=self.certificate_password.get() or None,
            **common,  # type: ignore[arg-type]
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
