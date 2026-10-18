"""
Pagina "Proteger": agrega o quita la contrasena de un PDF.
"""

from pathlib import Path

import customtkinter as ctk

from ... import core
from ...i18n import tr, trn
from .. import style
from ..icons import icon
from ..widgets import Card, FileField, PasswordField, format_size, muted_label, primary_button
from .base import BasePage

LOCK = tr("Proteger con contraseña")
UNLOCK = tr("Quitar contraseña")


class SecurityPage(BasePage):
    name = "Proteger"
    title = tr("Proteger PDF")
    subtitle = tr("Cifre un PDF con contraseña (AES-256) o genere una copia sin protección si conoce la clave.")
    icon_name = "protect"

    def build(self) -> None:
        self.mode = ctk.CTkSegmentedButton(
            self.body,
            values=[LOCK, UNLOCK],
            command=self._on_mode_selected,
            height=36,
            font=style.fonts().body,
        )
        self.mode.set(LOCK)
        self.mode.grid(row=0, column=0, sticky="w", pady=(0, style.GAP + 2))

        source = Card(self.body, tr("Documento"))
        source.grid(row=1, column=0, sticky="ew", pady=(0, style.GAP))
        self.source_field = FileField(
            source,
            source.row(0),
            "PDF",
            on_change=self._on_source_selected,
            placeholder=tr("Seleccione o arrastre un PDF"),
        )
        self.source_info = muted_label(source)
        self.source_info.grid(row=source.row(1), column=1, columnspan=2, sticky="ew", padx=(0, style.CARD_PAD))

        self.password_card = Card(self.body, tr("Contraseña"))
        self.password_card.grid(row=2, column=0, sticky="ew", pady=(0, style.GAP))
        self.password = PasswordField(self.password_card, self.password_card.row(0), tr("Contraseña"))
        self.confirmation = PasswordField(self.password_card, self.password_card.row(1), tr("Confirmar"))
        self.hint = muted_label(self.password_card)
        self.hint.grid(row=self.password_card.row(2), column=1, columnspan=2, sticky="ew", padx=(0, style.CARD_PAD))

        output = Card(self.body, tr("Resultado"))
        output.grid(row=3, column=0, sticky="ew", pady=(0, style.GAP))
        self.output_field = FileField(
            output, output.row(0), tr("Guardar como"), mode="save", initial_dir=lambda: self.app.settings.output_path
        )

        self.run_button = primary_button(self.body, "", self._run, "lock", width=190)
        self.run_button.grid(row=4, column=0, sticky="e", pady=(4, style.PAD))
        self._apply_mode()

    @property
    def locking(self) -> bool:
        return self.mode.get() == LOCK

    def _on_mode_selected(self, value: str) -> None:
        self.log("Accion: %s", "Proteger con contrasena" if value == LOCK else "Quitar contrasena")
        self._apply_mode()

    def _apply_mode(self) -> None:
        if self.locking:
            self.confirmation.show()
            self.hint.configure(
                text=tr(
                    "Mínimo {count} caracteres. Guárdela en un lugar seguro: no se puede recuperar.",
                    count=core.MIN_PASSWORD_LENGTH,
                )
            )
            self.run_button.configure(text=tr("Proteger PDF"), image=icon("lock", 16, style.ON_ACCENT))
        else:
            self.confirmation.hide()
            self.hint.configure(text=tr("Ingrese la contraseña actual del documento."))
            self.run_button.configure(text=tr("Quitar contraseña"), image=icon("unlock", 16, style.ON_ACCENT))
        source = self.resolved(self.source_field.path)
        if source is not None and self.output_field.auto:
            self._set_default_output(source)

    def _on_source_selected(self, path: Path) -> None:
        try:
            info = core.get_pdf_info(path)
        except core.PdfManagementError as error:
            self.log("PDF no valido: %s", error)
            self.source_info.configure(text=str(error), text_color=style.DANGER)
            return
        state = tr("Protegido con contraseña") if info.encrypted else tr("Sin protección")
        self.log(
            "PDF listo: %s (%s)",
            info.path.name,
            "protegido con contrasena" if info.encrypted else "sin proteccion",
            accion_sugerida="Quitar contrasena" if info.encrypted else "Proteger con contrasena",
        )
        pages = (
            trn("{count} página", "{count} páginas", info.page_count) + "  ·  " if info.page_count is not None else ""
        )
        self.source_info.configure(
            text=f"{pages}{format_size(info.size_bytes)}  ·  {state}", text_color=style.TEXT_MUTED
        )
        self.mode.set(UNLOCK if info.encrypted else LOCK)
        self._apply_mode()
        self._set_default_output(info.path)

    def _set_default_output(self, source: Path) -> None:
        self.output_field.set(
            self.default_output(source, tr("protegido") if self.locking else tr("sin_clave")), auto=True
        )

    def _run(self) -> None:
        def start() -> None:
            source = self.resolved(self.source_field.path)
            if source is None:
                raise core.InvalidInputError(tr("Seleccione el PDF."))
            password = self.password.get()
            if not password:
                raise core.InvalidInputError(tr("Ingrese la contraseña."))
            if self.locking and password != self.confirmation.get():
                raise core.InvalidInputError(tr("Las contraseñas no coinciden."))
            output = self.resolve_output(self.output_field)
            if output is None:
                return
            if self.locking:
                operation = lambda _passwords: core.lock_pdf(source, output, password)  # noqa: E731
                title, description, logged = tr("PDF protegido"), tr("Protegiendo PDF"), "Protegiendo PDF"
            else:
                operation = lambda passwords: core.unlock_pdf(source, output, passwords.get(source, password))  # noqa: E731
                title, description = tr("Protección eliminada"), tr("Quitando protección")
                logged = "Quitando proteccion"
            self.log("%s solicitado: %s", logged, source.name, salida=output)
            self.run_task(
                description,
                title,
                operation,
                button=self.run_button,
                on_success=lambda _result: self._clear_passwords(),
            )

        self.guard(start)

    def _clear_passwords(self) -> None:
        self.password.set("")
        self.confirmation.set("")
