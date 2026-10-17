"""
Pagina "Extraer": crea un PDF nuevo con las paginas seleccionadas.
"""

import tkinter as tk
from pathlib import Path

import customtkinter as ctk

from ... import core
from ...i18n import tr, trn
from .. import style
from ..widgets import (
    Card,
    FileField,
    PasswordField,
    field_label,
    format_size,
    muted_label,
    primary_button,
    secondary_button,
)
from .base import BasePage


class ExtractPage(BasePage):
    name = "Extraer"
    title = tr("Extraer páginas")
    subtitle = tr("Genere un PDF nuevo con solo las páginas que necesita, en el orden que indique.")
    icon_name = "extract"

    def build(self) -> None:
        self.page_count: int | None = None

        source = Card(self.body, tr("Documento de origen"))
        source.grid(row=0, column=0, sticky="ew", pady=(0, style.GAP))
        self.source_field = FileField(
            source,
            source.row(0),
            "PDF",
            on_change=self._on_source_selected,
            placeholder=tr("Seleccione o arrastre un PDF"),
            initial_dir=lambda: self.app.settings.output_path,
        )
        self.source_info = muted_label(source)
        self.source_info.grid(row=source.row(1), column=1, columnspan=2, sticky="ew", padx=(0, style.CARD_PAD))

        selection = Card(
            self.body,
            tr("Páginas"),
            tr("Páginas desde 1, separadas por comas. Ejemplos: 1-3, 8, 10-   ·   todo   ·   impar   ·   par"),
        )
        selection.grid(row=1, column=0, sticky="ew", pady=(0, style.GAP))
        self.selection = tk.StringVar()
        field_label(selection, tr("Selección")).grid(
            row=selection.row(0), column=0, sticky="w", padx=(style.CARD_PAD, style.GAP), pady=8
        )
        ctk.CTkEntry(selection, textvariable=self.selection, placeholder_text=tr("Ej.: 1-3, 8, 10-"), height=34).grid(
            row=selection.row(0), column=1, sticky="ew", pady=8
        )
        presets = ctk.CTkFrame(selection, fg_color="transparent")
        presets.grid(row=selection.row(0), column=2, padx=(8, style.CARD_PAD))
        for label, value in ((tr("Todas"), "todo"), (tr("Impares"), "impar"), (tr("Pares"), "par")):
            secondary_button(presets, label, lambda v=value: self._use_preset(v), width=72).pack(side="left", padx=2)
        self.selection_preview = muted_label(selection)
        self.selection_preview.grid(row=selection.row(1), column=1, columnspan=2, sticky="ew", padx=(0, style.CARD_PAD))
        self.selection.trace_add("write", lambda *_: self._update_preview())

        security = Card(self.body, tr("Contraseñas (opcional)"))
        security.grid(row=2, column=0, sticky="ew", pady=(0, style.GAP))
        self.source_password = PasswordField(
            security, security.row(0), tr("PDF de origen"), tr("Solo si el PDF está protegido")
        )
        self.output_password = PasswordField(
            security, security.row(1), tr("Proteger resultado"), tr("Deje vacío para no proteger")
        )

        output = Card(self.body, tr("Resultado"))
        output.grid(row=3, column=0, sticky="ew", pady=(0, style.GAP))
        self.output_field = FileField(
            output, output.row(0), tr("Guardar como"), mode="save", initial_dir=lambda: self.app.settings.output_path
        )
        self.run_button = primary_button(self.body, tr("Extraer páginas"), self._extract, "extract", width=170)
        self.run_button.grid(row=4, column=0, sticky="e", pady=(4, style.PAD))

    def _on_source_selected(self, path: Path) -> None:
        self.passwords.clear()
        self.page_count = None
        try:
            info = core.get_pdf_info(path)
        except core.PdfManagementError as error:
            self.log("Origen no valido: %s", error)
            self.source_info.configure(text=str(error), text_color=style.DANGER)
            return
        self.page_count = info.page_count
        self.log("Origen listo: %s", info.path.name, paginas=info.page_count or "?", protegido=info.encrypted)
        pages = (
            trn("{count} página", "{count} páginas", info.page_count)
            if info.page_count is not None
            else tr("Protegido con contraseña")
        )
        lock = "  ·  " + tr("protegido") if info.encrypted and info.page_count is not None else ""
        self.source_info.configure(
            text=f"{pages}  ·  {format_size(info.size_bytes)}{lock}", text_color=style.TEXT_MUTED
        )
        self.output_field.set(self.default_output(info.path, tr("páginas")), auto=True)
        self._update_preview()

    def _use_preset(self, value: str) -> None:
        self.log_debug("Seleccion rapida: %s", value)
        self.selection.set(value)

    def _update_preview(self) -> None:
        text = self.selection.get().strip()
        if not text or self.page_count is None:
            self.selection_preview.configure(text="")
            return
        try:
            indexes = core.parse_page_selection(text, self.page_count)
        except core.InvalidInputError as error:
            self.selection_preview.configure(text=str(error), text_color=style.DANGER)
            return
        shown = ", ".join(str(index + 1) for index in indexes[:15])
        more = f" ... (+{len(indexes) - 15})" if len(indexes) > 15 else ""
        self.selection_preview.configure(
            text=trn(
                "Se extraerá {count} página: {lista}",
                "Se extraerán {count} páginas: {lista}",
                len(indexes),
                lista=shown + more,
            ),
            text_color=style.SUCCESS,
        )

    def _extract(self) -> None:
        def start() -> None:
            source = self.resolved(self.source_field.path)
            if source is None:
                raise core.InvalidInputError(tr("Seleccione el PDF de origen."))
            selection = self.selection.get()
            if not selection.strip():
                raise core.InvalidInputError(tr("Indique las páginas a extraer."))
            output = self.resolve_output(self.output_field)
            if output is None:
                return
            typed_password = self.source_password.get() or None
            output_password = self.output_password.get() or None
            self.log(
                "Extraer paginas solicitado: %s",
                source.name,
                seleccion=selection.strip(),
                clave_origen=typed_password,
                proteger_resultado=bool(output_password),
                salida=output,
            )
            self.run_task(
                tr("Extrayendo páginas"),
                tr("Páginas extraídas"),
                lambda passwords: core.extract_pages(
                    source,
                    output,
                    selection,
                    password=passwords.get(source, typed_password),
                    output_password=output_password,
                ),
                button=self.run_button,
            )

        self.guard(start)
