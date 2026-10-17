"""
Barra de estado: informa que hace la aplicacion y el resultado de la ultima
operacion, con acceso directo al archivo generado.

Estados:

- ``idle``     Listo, sin operaciones en curso.
- ``busy``     Operacion en segundo plano (con barra de progreso y cola).
- ``success``  Ultimo archivo generado, con botones "Abrir" y "Mostrar en carpeta".
- ``error``    La ultima operacion no se completo.

Al pasar el cursor sobre el indicador o el mensaje se muestra un tooltip que
explica el estado actual.
"""

from datetime import datetime
from pathlib import Path

import customtkinter as ctk

from .. import paths
from ..i18n import tr, trn
from . import style
from .events import log_event
from .system import open_path, reveal_in_folder
from .widgets import ToolTip, hide, secondary_button, show

IDLE_HELP = tr(
    "Barra de estado\n"
    "Muestra el progreso de las operaciones (unir, extraer, convertir, firmar, proteger) "
    "y el resultado de la última. Al terminar podrá abrir el archivo generado o mostrarlo "
    "en su carpeta. Puede seguir usando la aplicación mientras una operación está en curso."
)

_DOT_COLORS = {
    "idle": style.TEXT_MUTED,
    "success": style.SUCCESS,
    "error": style.DANGER,
}


class StatusBar(ctk.CTkFrame):
    """Barra inferior con indicador de estado, mensaje, progreso y acciones."""

    def __init__(self, parent, on_view=None) -> None:
        super().__init__(parent, height=46, corner_radius=0, fg_color=style.SIDEBAR_BG)
        self.grid_columnconfigure(1, weight=1)
        self.state = "idle"
        self.last_result: Path | None = None
        self._help_text = IDLE_HELP

        ctk.CTkFrame(self, height=1, corner_radius=0, fg_color=style.CARD_BORDER).grid(
            row=0, column=0, columnspan=4, sticky="new"
        )

        self.pill = ctk.CTkFrame(
            self, corner_radius=14, fg_color=style.CARD_BG, border_width=1, border_color=style.CARD_BORDER
        )
        self.pill.grid(row=1, column=0, sticky="w", padx=(style.PAD, 10), pady=7)
        self.dot = ctk.CTkFrame(self.pill, width=10, height=10, corner_radius=5, fg_color=style.TEXT_MUTED)
        self.dot.grid(row=0, column=0, padx=(12, 8), pady=8)
        self.progress = ctk.CTkProgressBar(self.pill, width=80, height=6, mode="indeterminate")
        self.message = ctk.CTkLabel(self.pill, text="", font=style.fonts().body, text_color=style.TEXT, anchor="w")
        self.message.grid(row=0, column=2, sticky="w", padx=(0, 14))

        self.reveal_button = secondary_button(
            self,
            tr("Mostrar en carpeta"),
            lambda: self._use_result("Mostrar en carpeta", reveal_in_folder),
            "folder",
            width=150,
        )
        self.on_view = on_view
        self.view_button = secondary_button(
            self,
            tr("Ver en el visor"),
            lambda: self._use_result("Ver en el visor", self.on_view),
            "eye",
            width=150,
        )
        ToolTip(self.view_button, tr("Abre el archivo generado en la sección Visor"), above=True)
        self.open_button = ctk.CTkButton(
            self,
            text=tr("Abrir"),
            width=80,
            height=34,
            corner_radius=8,
            font=style.fonts().body,
            command=lambda: self._use_result("Abrir", open_path),
        )
        ToolTip(self.reveal_button, tr("Abre el explorador con el archivo seleccionado"), above=True)
        ToolTip(self.open_button, tr("Abre el archivo con el programa predeterminado"), above=True)

        for widget in (self.pill, self.dot, self.message):
            ToolTip(widget, lambda: self._help_text, above=True)
        self.set_idle()

    # * Estados -------------------------------------------------------------

    def set_idle(self) -> None:
        self._apply("idle", tr("Listo · sin operaciones en curso"), IDLE_HELP)
        self._hide_actions()

    def set_busy(self, description: str, pending: int) -> None:
        queued = "  " + trn("(+{count} en cola)", "(+{count} en cola)", pending - 1) if pending > 1 else ""
        self._apply(
            "busy",
            f"{description}...{queued}",
            tr(
                "Operación en curso: {task}.\nPuede seguir trabajando; el resultado aparecerá aquí al terminar.",
                task=description,
            ),
        )
        self._hide_actions()

    def set_success(self, title: str, result: Path, show_actions: bool = True) -> None:
        self.last_result = result
        finished = datetime.now().strftime("%H:%M")
        self._apply(
            "success",
            f"{title}: {result.name}  ·  {finished}",
            tr(
                "Última operación: {title} (terminó a las {time}).\nArchivo: {file}\n"
                "Use «Abrir» o «Mostrar en carpeta» para acceder al resultado.",
                title=title,
                time=finished,
                file=result,
            ),
        )
        if show_actions:
            if self.on_view is not None:
                self.view_button.grid(row=1, column=2, padx=(0, 8))
            self.reveal_button.grid(row=1, column=3, padx=(0, 8))
            self.open_button.grid(row=1, column=4, padx=(0, style.PAD))

    def set_error(self, summary: str) -> None:
        short = summary.splitlines()[0] if summary else tr("La operación no se completó")
        if len(short) > 90:
            short = short[:87] + "..."
        self._apply(
            "error",
            tr("No se completó: {reason}", reason=short),
            tr(
                "La última operación no se completó.\n{details}\n\nSi el problema persiste, revise {log}",
                details=summary,
                log=paths.LOG_DIR / "error.log",
            ),
        )
        self._hide_actions()

    # * Interno -------------------------------------------------------------

    def _use_result(self, action: str, handler) -> None:
        if self.last_result is None:
            return
        log_event("Barra de estado", "%s: %s", action, self.last_result.name, ruta=self.last_result)
        handler(self.last_result)

    def _apply(self, state: str, text: str, help_text: str) -> None:
        self.state = state
        self._help_text = help_text
        self.message.configure(text=text, text_color=style.DANGER if state == "error" else style.TEXT)
        if state == "busy":
            hide(self.dot)
            self.progress.grid(row=0, column=1, padx=(12, 10), pady=8)
            self.progress.start()
        else:
            self.progress.stop()
            hide(self.progress)
            show(self.dot)
            self.dot.configure(fg_color=_DOT_COLORS[state])

    def _hide_actions(self) -> None:
        hide(self.view_button)
        hide(self.reveal_button)
        hide(self.open_button)
