"""
Pagina "Proteger": agrega o quita la contrasena de un PDF.
"""

from pathlib import Path

import customtkinter as ctk

from ... import core
from .. import style
from ..icons import icon
from ..widgets import Card, FileField, PasswordField, format_size, muted_label, primary_button
from .base import BasePage

LOCK = "Proteger con contrasena"
UNLOCK = "Quitar contrasena"


class SecurityPage(BasePage):
    name = "Proteger"
    title = "Proteger PDF"
    subtitle = "Cifre un PDF con contrasena (AES-256) o genere una copia sin proteccion si conoce la clave."
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

        source = Card(self.body, "Documento")
        source.grid(row=1, column=0, sticky="ew", pady=(0, style.GAP))
        self.source_field = FileField(
            source,
            source.row(0),
            "PDF",
            on_change=self._on_source_selected,
            placeholder="Seleccione o arrastre un PDF",
        )
        self.source_info = muted_label(source)
        self.source_info.grid(row=source.row(1), column=1, columnspan=2, sticky="ew", padx=(0, style.CARD_PAD))

        self.password_card = Card(self.body, "Contrasena")
        self.password_card.grid(row=2, column=0, sticky="ew", pady=(0, style.GAP))
        self.password = PasswordField(self.password_card, self.password_card.row(0), "Contrasena")
        self.confirmation = PasswordField(self.password_card, self.password_card.row(1), "Confirmar")
        self.hint = muted_label(self.password_card)
        self.hint.grid(row=self.password_card.row(2), column=1, columnspan=2, sticky="ew", padx=(0, style.CARD_PAD))

        output = Card(self.body, "Resultado")
        output.grid(row=3, column=0, sticky="ew", pady=(0, style.GAP))
        self.output_field = FileField(
            output, output.row(0), "Guardar como", mode="save", initial_dir=lambda: self.app.settings.output_path
        )

        self.run_button = primary_button(self.body, "", self._run, "lock", width=190)
        self.run_button.grid(row=4, column=0, sticky="e", pady=(4, style.PAD))
        self._apply_mode()

    @property
    def locking(self) -> bool:
        return self.mode.get() == LOCK

    def _on_mode_selected(self, value: str) -> None:
        self.log("Accion: %s", value)
        self._apply_mode()

    def _apply_mode(self) -> None:
        if self.locking:
            self.confirmation.show()
            self.hint.configure(
                text=f"Minimo {core.MIN_PASSWORD_LENGTH} caracteres. "
                "Guardela en un lugar seguro: no se puede recuperar."
            )
            self.run_button.configure(text="Proteger PDF", image=icon("lock", 16, style.WHITE))
        else:
            self.confirmation.hide()
            self.hint.configure(text="Ingrese la contrasena actual del documento.")
            self.run_button.configure(text="Quitar contrasena", image=icon("unlock", 16, style.WHITE))
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
        state = "Protegido con contrasena" if info.encrypted else "Sin proteccion"
        self.log(
            "PDF listo: %s (%s)",
            info.path.name,
            state.lower(),
            accion_sugerida=UNLOCK if info.encrypted else LOCK,
        )
        pages = f"{info.page_count} paginas  ·  " if info.page_count is not None else ""
        self.source_info.configure(
            text=f"{pages}{format_size(info.size_bytes)}  ·  {state}", text_color=style.TEXT_MUTED
        )
        self.mode.set(UNLOCK if info.encrypted else LOCK)
        self._apply_mode()
        self._set_default_output(info.path)

    def _set_default_output(self, source: Path) -> None:
        self.output_field.set(self.default_output(source, "protegido" if self.locking else "sin_clave"), auto=True)

    def _run(self) -> None:
        def start() -> None:
            source = self.resolved(self.source_field.path)
            if source is None:
                raise core.InvalidInputError("Seleccione el PDF.")
            password = self.password.get()
            if not password:
                raise core.InvalidInputError("Ingrese la contrasena.")
            if self.locking and password != self.confirmation.get():
                raise core.InvalidInputError("Las contrasenas no coinciden.")
            output = self.resolve_output(self.output_field)
            if output is None:
                return
            if self.locking:
                operation = lambda _passwords: core.lock_pdf(source, output, password)  # noqa: E731
                title, description = "PDF protegido", "Protegiendo PDF"
            else:
                operation = lambda passwords: core.unlock_pdf(source, output, passwords.get(source, password))  # noqa: E731
                title, description = "Proteccion eliminada", "Quitando proteccion"
            self.log("%s solicitado: %s", description, source.name, salida=output)
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
