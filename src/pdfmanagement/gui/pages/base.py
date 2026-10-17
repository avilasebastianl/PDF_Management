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
from ..events import debug_event, log_event
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
    show_header: bool = True  # False: sin titulo grande, para secciones que necesitan todo el espacio (Visor)

    def __init__(self, master, app: MainWindow) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.app = app
        self.log_area = self.name  # seccion para el registro de eventos (ver events.area_of)
        self.passwords: Passwords = {}

        if self.show_header:
            PageHeader(self, self.title, self.subtitle).pack(fill="x", padx=style.PAD, pady=(style.PAD, style.GAP))
        pad = style.PAD if self.show_header else style.COMPACT_PAD
        if self.scrollable:
            self.body = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
            self.body.pack(fill="both", expand=True, padx=(pad - 6, 6), pady=(0 if self.show_header else pad, 0))
        else:
            self.body = ctk.CTkFrame(self, fg_color="transparent", corner_radius=0)
            self.body.pack(fill="both", expand=True, padx=pad, pady=(0 if self.show_header else pad, 0))
        self.body.grid_columnconfigure(0, weight=1)
        self.build()

    # * Ciclo de vida -----------------------------------------------------

    def build(self) -> None:
        raise NotImplementedError

    def on_show(self) -> None:
        """Se invoca cada vez que la pagina se vuelve visible."""

    def on_hide(self) -> None:
        """Se invoca al dejar de mostrar la pagina (otra seccion pasa al frente)."""

    def flush_layout(self) -> None:
        """Aplica ya los reacomodos pendientes (p. ej. del visor) antes de una animacion."""
        view = getattr(self, "view", None)
        if view is not None and hasattr(view, "flush_resize"):
            view.flush_resize()
            view.scheduler.drain()  # las paginas visibles quedan dibujadas antes de moverse

    def begin_slide(self, center_shift: float) -> float:
        """
        Antes de deslizar la seccion: reacomoda el visor a su ancho final y
        devuelve cuanto hay que desplazar sus paginas para que no salten de
        lado (0 si no hace falta). ``center_shift`` es cuanto se movio el
        centro del contenido al cambiar de ancho.
        """
        self.flush_layout()
        view = getattr(self, "view", None)
        if view is None or not hasattr(view, "slide_offset") or view.zoom_mode == "fit_width":
            return 0.0  # ajustado al ancho, la pagina ya ocupa todo: no salta de lado
        view.slide_offset(center_shift)
        return center_shift

    def slide_content(self, offset: float) -> None:
        view = getattr(self, "view", None)
        if view is not None and hasattr(view, "slide_offset"):
            view.slide_offset(offset)

    def pause_rendering(self, paused: bool) -> None:
        """Pausa o reanuda el dibujo de paginas del visor de la seccion (durante animaciones)."""
        view = getattr(self, "view", None)
        if view is not None and hasattr(view, "scheduler"):
            view.scheduler.pause(paused)

    def can_close(self) -> bool:
        """Antes de cerrar la ventana: ``False`` la mantiene abierta (p. ej. cambios sin guardar)."""
        return True

    def on_close(self) -> None:
        """Se invoca al cerrar la aplicacion (liberar recursos)."""

    # * Registro --------------------------------------------------------------

    def log(self, message: str, *args, **details) -> None:
        """Evento de esta seccion (nivel INFO)."""
        log_event(self.log_area, message, *args, **details)

    def log_debug(self, message: str, *args, **details) -> None:
        """Evento de esta seccion visible solo en modo detallado."""
        debug_event(self.log_area, message, *args, **details)

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
            self.log_debug("Salida sugerida ya existia; se usa un nombre libre", archivo=output.name)
            return output
        if field.confirmed_path and field.confirmed_path.resolve() == output.resolve():
            self.log_debug("Se reemplazara el archivo confirmado en 'Guardar como'", archivo=output.name)
            return output
        replace = messagebox.askyesno(
            "Archivo existente",
            f"'{output.name}' ya existe.\n\nDesea reemplazarlo?",
            parent=self,
        )
        self.log(
            "Archivo de salida existente: %s", "se reemplaza" if replace else "operacion cancelada", archivo=output.name
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
                retry = isinstance(error, core.WrongPasswordError)
                self.log(
                    "Se pide la contrasena de %s%s",
                    error.file_path.name,
                    " (la anterior no era correcta)" if retry else "",
                )
                password = ask_password(self, error.file_path.name, retry=retry)
                self.log("Contrasena %s", "ingresada; se reintenta" if password else "cancelada por el usuario")
                if password:
                    self.passwords[error.file_path] = password
                    self.run_task(description, success_title, operation, button=button, on_success=on_success)
                return
            self.app.show_error(error)

        passwords = dict(self.passwords)
        self.app.runner.submit(description, lambda: operation(passwords), succeeded, failed)

    def receive_file(self, path: Path) -> None:
        """
        Recibe un archivo enviado desde otra seccion (p. ej. el Visor). Por
        defecto lo pone como archivo de origen si la pagina tiene uno.
        """
        source_field = getattr(self, "source_field", None)
        if source_field is None:
            return
        self.log("Archivo recibido de otra seccion: %s", path.name)
        source_field.set(path)

    def guard(self, action: Callable[[], None]) -> None:
        """Ejecuta una accion de la interfaz mostrando los errores de validacion."""
        try:
            action()
        except Exception as error:
            self.app.show_error(error)

    @staticmethod
    def resolved(path: Path | None) -> Path | None:
        return path.expanduser().resolve() if path else None
