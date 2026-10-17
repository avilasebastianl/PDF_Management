"""
Cambio de tema (claro / oscuro) fluido.

CustomTkinter redibuja, uno por uno, todos los widgets registrados al cambiar
el modo de apariencia (~1,2 s con todas las secciones construidas) y Windows
pinta la ventana a medida que cambian, lo que se ve como un barrido lento.

``AppearanceScheduler`` reemplaza ese recorrido para:

1. Redibujar primero solo lo visible (barra lateral, seccion actual, barra de
   estado y ventanas secundarias), con el pintado de la ventana congelado, de
   modo que el cambio aparece completo en un solo cuadro.
2. Actualizar las secciones ocultas despues, por lotes con un presupuesto de
   tiempo, sin bloquear la interfaz. Si el usuario abre una seccion pendiente,
   se actualiza justo antes de mostrarse.

Funciona tanto con el interruptor de la aplicacion como con el modo "Sistema"
(cuando Windows cambia de tema), porque intercepta el punto unico por el que
CustomTkinter notifica a los widgets.
"""

import ctypes
import logging
import sys
import time
import tkinter
from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import customtkinter as ctk

logger = logging.getLogger(__name__)

BATCH_BUDGET_MS = 25   # tiempo maximo por lote al actualizar secciones ocultas
BATCH_PAUSE_MS = 1     # pausa entre lotes para atender eventos del usuario

_OFFSCREEN = 0          # grupo de widgets de la seccion actual que no estan a la vista
_MISSING = object()

_WM_SETREDRAW = 0x000B
# INVALIDATE|ALLCHILDREN|UPDATENOW|FRAME. Sin ERASE: borrar el fondo antes de que Tk
# pinte se veia como un destello al reactivar el pintado.
_RDW_FLAGS = 0x0001 | 0x0080 | 0x0100 | 0x0400


@contextmanager
def frozen_redraw(root) -> Iterator[None]:
    """
    Suspende el pintado de la ventana (solo Windows) y al terminar la repinta
    completa de una vez. En otros sistemas no hace nada.
    """
    if not sys.platform.startswith("win"):
        yield
        return
    user32 = ctypes.windll.user32
    hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
    user32.SendMessageW(hwnd, _WM_SETREDRAW, 0, 0)
    try:
        yield
        root.update_idletasks()
    finally:
        user32.SendMessageW(hwnd, _WM_SETREDRAW, 1, 0)
        user32.RedrawWindow(hwnd, None, None, _RDW_FLAGS)


class AppearanceScheduler:
    """
    Prioriza lo visible al cambiar de tema y difiere las secciones ocultas.

    Args:
        root: Ventana principal.
        hidden_pages: Funcion que devuelve las secciones que no se ven ahora.
    """

    def __init__(self, root, hidden_pages: Callable[[], list]) -> None:
        self.root = root
        self.hidden_pages = hidden_pages
        self._pending: dict[int, deque[Callable[[str], None]]] = {}
        self._mode = "Light"
        self._job: str | None = None
        self._install()

    # * Integracion con CustomTkinter -----------------------------------------

    def _install(self) -> None:
        scheduler = self
        tracker_class = ctk.AppearanceModeTracker
        self._original = tracker_class.__dict__["update_callbacks"]
        # Si quedo instalado otro planificador (ventana anterior), se conserva el original real.
        self._original = getattr(self._original, "__pdfmanagement_original__", self._original)

        def update_callbacks(tracker) -> None:
            scheduler._apply("Dark" if tracker.appearance_mode == 1 else "Light", list(tracker.callback_list))

        patched = classmethod(update_callbacks)
        patched.__pdfmanagement_original__ = self._original
        tracker_class.update_callbacks = patched

    def uninstall(self) -> None:
        """Restaura el comportamiento original de CustomTkinter (al cerrar la ventana)."""
        self._cancel_job()
        self._pending.clear()
        ctk.AppearanceModeTracker.update_callbacks = self._original

    # * Aplicacion ----------------------------------------------------------

    def _apply(self, mode: str, callbacks: list[Callable[[str], None]]) -> None:
        started = time.perf_counter()
        self._mode = mode
        self._cancel_job()
        hidden = {id(page): page for page in self.hidden_pages()}
        visible: list[Callable[[str], None]] = []
        # Primero lo que esta en la seccion actual pero fuera de la vista (p. ej.
        # filas de una lista con scroll); despues las secciones ocultas.
        pending: dict[int, deque[Callable[[str], None]]] = {_OFFSCREEN: deque()}
        clip_cache: dict[int, tuple[int, int, int, int] | None] = {}
        for callback in callbacks:
            owner = self._hidden_owner(callback, hidden)
            if owner is not None:
                pending.setdefault(owner, deque()).append(callback)
            elif self._on_screen(getattr(callback, "__self__", None), clip_cache):
                visible.append(callback)
            else:
                pending[_OFFSCREEN].append(callback)
        if not pending[_OFFSCREEN]:
            del pending[_OFFSCREEN]

        with frozen_redraw(self.root):
            self._run(visible)
        self._pending = pending
        logger.debug(
            "Tema %s: %d widgets visibles en %.0f ms, %d diferidos",
            mode, len(visible), (time.perf_counter() - started) * 1000, sum(map(len, pending.values())),
        )
        if pending:
            self._job = self.root.after(BATCH_PAUSE_MS, self._process_batch)

    def flush_page(self, page) -> None:
        """Actualiza ya los widgets pendientes de ``page`` (antes de mostrarla)."""
        callbacks = self._pending.pop(id(page), None)
        if callbacks:
            with frozen_redraw(self.root):
                self._run(callbacks)

    def _process_batch(self) -> None:
        self._job = None
        deadline = time.perf_counter() + BATCH_BUDGET_MS / 1000
        while self._pending and time.perf_counter() < deadline:
            owner = next(iter(self._pending))
            callbacks = self._pending[owner]
            callback = callbacks.popleft()
            if not callbacks:
                del self._pending[owner]
            try:
                callback(self._mode)
            except Exception:  # noqa: BLE001 - p. ej. un widget ya destruido
                continue
        if self._pending:
            self._job = self.root.after(BATCH_PAUSE_MS, self._process_batch)

    def _run(self, callbacks) -> None:
        for callback in callbacks:
            try:
                callback(self._mode)
            except Exception:  # noqa: BLE001 - mismo criterio que CustomTkinter
                continue

    def _cancel_job(self) -> None:
        if self._job is not None:
            self.root.after_cancel(self._job)
            self._job = None

    @staticmethod
    def _on_screen(widget, clip_cache: dict) -> bool:
        """
        Indica si alguna parte del widget se ve: esta mapeado y su rectangulo
        no queda recortado por ningun contenedor (por ejemplo un area con scroll).
        """
        if widget is None or not hasattr(widget, "winfo_ismapped"):
            return True
        try:
            if isinstance(widget, (tkinter.Tk, tkinter.Toplevel)):
                return True
            if not widget.winfo_ismapped():
                return False
            x0, y0 = widget.winfo_rootx(), widget.winfo_rooty()
            x1, y1 = x0 + widget.winfo_width(), y0 + widget.winfo_height()
            ancestor = widget.master
            while ancestor is not None and not isinstance(ancestor, (tkinter.Tk, tkinter.Toplevel)):
                rect = clip_cache.get(id(ancestor), _MISSING)
                if rect is _MISSING:
                    ax, ay = ancestor.winfo_rootx(), ancestor.winfo_rooty()
                    rect = (ax, ay, ax + ancestor.winfo_width(), ay + ancestor.winfo_height())
                    clip_cache[id(ancestor)] = rect
                x0, y0, x1, y1 = max(x0, rect[0]), max(y0, rect[1]), min(x1, rect[2]), min(y1, rect[3])
                if x0 >= x1 or y0 >= y1:
                    return False
                ancestor = ancestor.master
        except tkinter.TclError:
            return True
        return True

    @staticmethod
    def _hidden_owner(callback, hidden: dict[int, object]) -> int | None:
        """Devuelve el id de la seccion oculta que contiene al widget del callback."""
        widget = getattr(callback, "__self__", None)
        while widget is not None:
            if id(widget) in hidden:
                return id(widget)
            widget = getattr(widget, "master", None)
        return None
