# mypy: disable-error-code="misc"
# (self anotado como ViewerPage, su subclase: mypy lo marca, pero comprueba igual los atributos)
"""
Pestanas de documentos: cada una con su sesion y como se estaba viendo.

Parte de ``ViewerPage`` (ver ``viewer.py``): los metodos anotan ``self`` con
``ViewerPage`` para que mypy compruebe los atributos que usan.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ...core.editing import DocumentSession
from ..viewer import FIT_WIDTH
from ..viewer.tab_strip import TabInfo
from .viewer_modes import FULLSCREEN

if TYPE_CHECKING:
    from .viewer import ViewerPage

MAX_TABS = 12


@dataclass
class DocumentTab:
    """Un documento abierto en el visor y como se estaba viendo."""

    session: DocumentSession
    saved_path: Path | None = None  # ultimo "Guardar como"
    signatures_confirmed: bool = False  # ya se aviso que editar invalida sus firmas
    page: int = 0
    zoom: str | float = FIT_WIDTH
    scroll: float | None = None  # posicion vertical (0-1) al dejar la pestana
    selection: list[int] = field(default_factory=list)
    unsubscribe: Callable[[], None] | None = None  # baja de los avisos de cambios de la sesion
    temp_folder: Path | None = None  # documento nuevo: vive en una carpeta temporal hasta "Guardar como"

    def release(self) -> None:
        """Cierra la sesion y borra la carpeta temporal (documentos nuevos)."""
        if self.unsubscribe is not None:
            self.unsubscribe()
        self.session.close()
        if self.temp_folder is not None:
            shutil.rmtree(self.temp_folder, ignore_errors=True)

    @property
    def path(self) -> Path:
        return self.saved_path or self.session.path


class TabsMixin:
    """Pestanas de documentos: cada una con su sesion y como se estaba viendo."""

    @property
    def tab(self: ViewerPage) -> DocumentTab | None:
        return self.tabs[self.active] if 0 <= self.active < len(self.tabs) else None

    @property
    def session(self: ViewerPage) -> DocumentSession | None:
        return self.tab.session if self.tab is not None else None

    @property
    def saved_path(self: ViewerPage) -> Path | None:
        return self.tab.saved_path if self.tab is not None else None

    @saved_path.setter
    def saved_path(self: ViewerPage, value: Path | None) -> None:
        if self.tab is not None:
            self.tab.saved_path = value

    @property
    def _signatures_confirmed(self: ViewerPage) -> bool:
        return self.tab.signatures_confirmed if self.tab is not None else False

    @_signatures_confirmed.setter
    def _signatures_confirmed(self: ViewerPage, value: bool) -> None:
        if self.tab is not None:
            self.tab.signatures_confirmed = value

    def _find_tab(self: ViewerPage, path: Path) -> int | None:
        target = path.resolve()
        for index, tab in enumerate(self.tabs):
            if target in (tab.session.path.resolve(), tab.path.resolve()):
                return index
        return None

    def switch_to(self: ViewerPage, index: int) -> None:
        """Muestra la pestana ``index`` recordando como se estaba viendo la actual."""
        if not 0 <= index < len(self.tabs):
            return
        if index != self.active:
            self._remember_view()
            self.active = index
            self._load_tab()
            self.log_debug("Pestana: %s", self.tabs[index].path.name, posicion=index + 1, total=len(self.tabs))
        self._render_tabs()

    def cycle_tab(self: ViewerPage, step: int) -> None:
        if len(self.tabs) > 1:
            self.switch_to((self.active + step) % len(self.tabs))

    def _close_tab_clicked(self: ViewerPage, index: int) -> None:
        self.close_tab(index)

    def close_current_tab(self: ViewerPage) -> None:
        if self.tab is not None:
            self.close_tab(self.active)

    def close_tab(self: ViewerPage, index: int, confirm: bool = True) -> bool:
        """Cierra una pestana; con cambios sin guardar pregunta antes (si ``confirm``)."""
        if not 0 <= index < len(self.tabs):
            return False
        if confirm and self.tabs[index].session.modified:
            self.switch_to(index)  # que se vea cual es
            if not self._confirm_discard("cerrar la pestana"):
                return False
        was_active = index == self.active
        if was_active:
            self.search.set_document(None)
            self.view.set_document(None)
        tab = self.tabs.pop(index)
        self.forget_compared(tab)
        tab.release()
        if was_active:
            self.active = min(index, len(self.tabs) - 1)
            self._load_tab()
        elif index < self.active:
            self.active -= 1
        self._render_tabs()
        self.log("Pestana cerrada", archivo=tab.path.name, quedan=len(self.tabs))
        return True

    def close_all_documents(self: ViewerPage, confirm: bool = False) -> bool:
        while self.tabs:
            if not self.close_tab(len(self.tabs) - 1, confirm=confirm):
                return False
        return True

    def _remember_view(self: ViewerPage) -> None:
        tab = self.tab
        if tab is None or not self.view.sizes:
            return
        tab.page = self.view.current_page
        tab.zoom = self.view.zoom_mode
        tab.scroll = self.view.canvas.yview()[0]
        tab.selection = sorted(self.thumbnails.selected)

    def _load_tab(self: ViewerPage) -> None:
        """Pone en el visor el documento de la pestana activa (o ninguno)."""
        tab = self.tab
        self.annotations.cancel_tool()
        self.annotations.selected = None
        self.find_bar.hide()
        self.text_tool.clear(self.view)
        self.selection_label.configure(text="")
        self.thumbnails.set_selection([])
        if tab is None:
            self.search.set_document(None)
            self.view.set_document(None)
            self.thumbnails.rebuild()
            self.outline.set_entries([])
        else:
            session = tab.session
            self.view.set_document(session.document, page=tab.page)
            if tab.zoom != self.view.zoom_mode:
                self.view.set_zoom(tab.zoom)
            if tab.scroll is not None and self.view.continuous:
                self.view.canvas.yview_moveto(tab.scroll)  # vuelve exactamente a donde estaba
                self.view._schedule_update()  # noqa: SLF001
            self.thumbnails.rebuild()
            self.thumbnails.set_selection(tab.selection)
            self.outline.set_entries(session.table_of_contents())
            self.search.set_document(session.document)
        self.annotations.reset()
        self._refresh_file_state()
        self.document_shown()

    def _render_tabs(self: ViewerPage) -> None:
        """Vuelve a dibujar la barra de pestanas (al abrir, cerrar o cambiar de pestana)."""
        if not self.tabs:
            self.tab_bar.set_tabs([], -1)
            self.tab_bar.grid_remove()
            return
        if self.view_mode != FULLSCREEN:
            self.tab_bar.grid()
        self.tab_bar.set_tabs([self._tab_info(tab) for tab in self.tabs], self.active)

    @staticmethod
    def _tab_info(tab: DocumentTab) -> TabInfo:
        return TabInfo(title=tab.path.name, tooltip=str(tab.path), modified=tab.session.modified)

    def _update_tab_title(self: ViewerPage) -> None:
        if self.tab is not None:
            self.tab_bar.update_tab(self.active, self._tab_info(self.tab))

    def _close_session(self: ViewerPage) -> None:
        """Cierra la pestana activa sin preguntar."""
        if self.tab is not None:
            self.close_tab(self.active, confirm=False)

    def can_close(self: ViewerPage) -> bool:
        """Al cerrar la aplicacion pregunta por cada pestana con cambios sin guardar."""
        for index, tab in enumerate(self.tabs):
            if tab.session.modified:
                self.switch_to(index)
                if not self._confirm_discard("cerrar la aplicacion"):
                    return False
        return True

    def on_close(self: ViewerPage) -> None:
        self.close_compare(log=False)
        self.search.set_document(None)
        self.view.set_document(None)
        for tab in self.tabs:
            tab.release()
        self.tabs.clear()
        self.active = -1
