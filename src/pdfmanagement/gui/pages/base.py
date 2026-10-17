"""
Clase base de las paginas: encabezado, ejecucion de tareas, reintento con
contrasena y control de sobrescritura de archivos.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox
from typing import TYPE_CHECKING

import customtkinter as ctk

from ... import core
from .. import style
from ..dialogs import ask_password
from ..widgets import FileField, PageHeader

if TYPE_CHECKING:
    from ..app import MainWindow

Passwords = dict[Path, str]


class BasePage(ctk.CTkFrame):
    """
    Pagina de la aplicacion. Las subclases definen ``name``, ``title``,
    ``subtitle`` e ``icon_name`` e implementan ``build``.
    """

    name: str = ""
    title: str = ""
    subtitle: str = ""
    icon_name: str = ""
    scrollable: bool = True

    def __init__(self, master, app: MainWindow) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.app = app
        self.passwords: Passwords = {}

        PageHeader(self, self.title, self.subtitle).pack(fill="x", padx=style.PAD, pady=(style.PAD, style.GAP))
        if self.scrollable:
            self.body = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
            self.body.pack(fill="both", expand=True, padx=(style.PAD - 6, 6), pady=(0, 0))
        else:
            self.body = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
            self.body.pack(fill="both", expand=True, padx=style.PAD)
        self.body.grid_columnconfigure(0, weight=1)
        self.build()

    # * Ciclo de vida -----------------------------------------------------

    def build(self) -> None:
        raise NotImplementedError

    def on_show(self) -> None:
        """Se invoca cada vez que la pagina se vuelve visible."""

    def on_close(self) -> None:
        """Se invoca al cerrar la aplicacion (liberar recursos)."""

    # * Utilidades ----------------------------------------------------------

    def default_output(self, source: Path, suffix: str) -> Path:
        """``<carpeta de salida>/<nombre>_<sufijo>.pdf`` sin sobrescribir archivos existentes."""
        name = f"{source.stem}_{suffix}.pdf" if suffix else f"{source.stem}.pdf"
        return core.unique_path(self.app.settings.output_path / name)

    def resolve_output(self, field: FileField) -> Path | None:
        """
        Devuelve la ruta de salida lista para usar o ``None`` si el usuario
        cancela. Nunca sobrescribe en silencio un archivo existente:

        - Ruta generada automaticamente: se busca un nombre libre.
        - Ruta confirmada en el dialogo "Guardar como": se respeta.
        - Ruta escrita a mano: se pide confirmacion.
        """
        output = field.path
        if output is None:
            raise core.InvalidInputError("Debe indicar el archivo de salida.")
        if output.suffix.lower() != ".pdf":
            output = output.with_name(output.name + ".pdf")
        if not output.exists():
            return output
        if field.auto:
            output = core.unique_path(output)
            field.set(output, auto=True, notify=False)
            return output
        if field.confirmed_path and field.confirmed_path.resolve() == output.resolve():
            return output
        replace = messagebox.askyesno(
            "Archivo existente",
            f"'{output.name}' ya existe.\n\nDesea reemplazarlo?",
            parent=self,
        )
        return output if replace else None

    def run_task(
        self,
        description: str,
        success_title: str,
        operation: Callable[[Passwords], Path],
        *,
        button: ctk.CTkButton | None = None,
        on_success: Callable[[Path], None] | None = None,
    ) -> None:
        """
        Ejecuta ``operation`` en segundo plano.

        ``operation`` recibe el diccionario de contrasenas de la pagina. Si
        falla por un PDF protegido, se pide la contrasena y se reintenta.
        """
        if button is not None:
            button.configure(state="disabled")

        def succeeded(result: Path) -> None:
            if button is not None:
                button.configure(state="normal")
            if on_success:
                on_success(result)
            self.app.notify_success(success_title, result)

        def failed(error: BaseException) -> None:
            if button is not None:
                button.configure(state="normal")
            if isinstance(error, core.PasswordRequiredError):
                password = ask_password(
                    self, error.file_path.name, retry=isinstance(error, core.WrongPasswordError)
                )
                if password:
                    self.passwords[error.file_path] = password
                    self.run_task(description, success_title, operation, button=button, on_success=on_success)
                return
            self.app.show_error(error)

        passwords = dict(self.passwords)
        self.app.runner.submit(description, lambda: operation(passwords), succeeded, failed)

    def guard(self, action: Callable[[], None]) -> None:
        """Ejecuta una accion de la interfaz mostrando los errores de validacion."""
        try:
            action()
        except Exception as error:  # noqa: BLE001 - se informa al usuario
            self.app.show_error(error)

    @staticmethod
    def resolved(path: Path | None) -> Path | None:
        return path.expanduser().resolve() if path else None
