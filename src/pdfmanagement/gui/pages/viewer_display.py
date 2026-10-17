# mypy: disable-error-code="misc"
# (self anotado como ViewerPage, su subclase: mypy lo marca, pero comprueba igual los atributos)
"""
Opciones de lectura del Visor: modo nocturno, dos paginas, comparar
documentos (vista dividida), imprimir y el panel de firmas digitales.

Parte de ``ViewerPage`` (ver ``viewer.py``): los metodos anotan ``self`` con
``ViewerPage`` para que mypy compruebe los atributos que usan.
"""

from __future__ import annotations

import tkinter as tk
from functools import partial
from typing import TYPE_CHECKING

from ... import core
from ...core import printing
from ...core.editing.changes import STRUCTURE, DocumentChange
from ...core.verify import verify_signatures
from ...i18n import tr, trn
from ..viewer.compare import ComparePanel
from ..widgets import set_enabled

if TYPE_CHECKING:
    from .viewer import ViewerPage
    from .viewer_tabs import DocumentTab


class DisplayMixin:
    """Modo nocturno, dos paginas, comparar, imprimir y firmas."""

    # * Modo nocturno y dos paginas (preferencias que se recuerdan) ----------------

    def apply_display_settings(self: ViewerPage) -> None:
        settings = self.app.settings
        self.night_mode = tk.BooleanVar(value=settings.viewer_night_mode)
        self.two_pages = tk.BooleanVar(value=settings.viewer_two_pages)
        self.view.set_inverted(settings.viewer_night_mode)
        self.view.set_spread(settings.viewer_two_pages)

    def set_night_mode(self: ViewerPage, enabled: bool) -> None:
        self.night_mode.set(enabled)
        for view in self._views():
            view.set_inverted(enabled)
        self.app.settings.viewer_night_mode = enabled
        self.app.save_settings()
        self.log("Modo nocturno: %s", "activado" if enabled else "desactivado")

    def set_two_pages(self: ViewerPage, enabled: bool) -> None:
        self.two_pages.set(enabled)
        for view in self._views():
            view.set_spread(enabled)
        self.app.settings.viewer_two_pages = enabled
        self.app.save_settings()
        self.log("Vista de dos paginas: %s", "activada" if enabled else "desactivada")

    def _views(self: ViewerPage):
        yield self.view
        if self.compare is not None:
            yield self.compare.view

    def show_view_menu(self: ViewerPage) -> None:
        """Menu del boton "Ver": opciones de lectura, comparar e imprimir."""
        menu = tk.Menu(self, tearoff=0)
        menu.add_checkbutton(
            label=tr("Modo nocturno"),
            variable=self.night_mode,
            command=lambda: self.set_night_mode(self.night_mode.get()),
        )
        menu.add_checkbutton(
            label=tr("Dos páginas"),
            variable=self.two_pages,
            command=lambda: self.set_two_pages(self.two_pages.get()),
        )
        menu.add_separator()
        others = tk.Menu(menu, tearoff=0)
        for index, tab in enumerate(self.tabs):
            if index != self.active:
                others.add_command(label=tab.path.name, command=partial(self.compare_with, index))
        if self.tabs:
            others.add_separator()
        others.add_command(label=tr("Otro PDF..."), command=self.compare_with_file)
        menu.add_cascade(label=tr("Comparar con"), menu=others, state="normal" if self.tabs else "disabled")
        if self.compare_tab is not None:
            menu.add_command(label=tr("Cerrar la comparación"), command=self.close_compare)
        menu.add_separator()
        menu.add_command(
            label=tr("Imprimir..."),
            accelerator="Ctrl+P",
            command=self.print_document,
            state="normal" if self.session is not None else "disabled",
        )
        button = self.view_button
        try:
            menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())
        finally:
            menu.grab_release()

    # * Comparar (vista dividida) -------------------------------------------------

    def compare_with(self: ViewerPage, index: int) -> None:
        """Muestra la pestana ``index`` junto al documento activo."""
        if not 0 <= index < len(self.tabs) or index == self.active:
            return
        self.close_compare(log=False)
        tab = self.tabs[index]
        panel = self._compare_panel()
        panel.set_title(tab.path.name)
        panel.view.set_inverted(self.night_mode.get())
        panel.view.set_spread(self.two_pages.get())
        panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self.view_area.grid_columnconfigure(1, weight=1, uniform="compare")
        self.view_area.grid_columnconfigure(0, uniform="compare")
        start = self.view.current_page if panel.sync.get() else 0
        panel.view.set_document(tab.session.document, page=min(start, tab.session.page_count - 1))
        self.compare_tab = tab
        self._compare_unsubscribe = tab.session.changes.subscribe(self._on_compared_changed)
        self.log("Comparando con %s", tab.path.name)

    def compare_with_file(self: ViewerPage) -> None:
        """Abre otro PDF y lo compara con el documento que se estaba viendo."""
        previous = self.tab
        count = len(self.tabs)
        self.browse()
        if previous is None or len(self.tabs) == count or self.tab is previous:
            return
        # El PDF nuevo queda activo; se compara con el que se estaba viendo.
        self.compare_with(self.tabs.index(previous))

    def close_compare(self: ViewerPage, log: bool = True) -> None:
        if self.compare_tab is None or self.compare is None:
            return
        if self._compare_unsubscribe is not None:
            self._compare_unsubscribe()
            self._compare_unsubscribe = None
        self.compare.view.set_document(None)
        self.compare.grid_remove()
        self.view_area.grid_columnconfigure(1, weight=0, uniform="")
        self.view_area.grid_columnconfigure(0, uniform="")
        self.compare_tab = None
        if log:
            self.log("Comparacion cerrada")

    def forget_compared(self: ViewerPage, tab: DocumentTab) -> None:
        """Se cierra una pestana: si era la comparada, termina la comparacion."""
        if tab is self.compare_tab:
            self.close_compare()

    def _compare_panel(self: ViewerPage) -> ComparePanel:
        panel = self.compare
        if panel is None:
            panel = self.compare = ComparePanel(self.view_area, on_close=self.close_compare)
            panel.view.on_page_changed(self._on_compare_page)
        return panel

    def sync_compare(self: ViewerPage, page: int) -> None:
        """La vista principal cambio de pagina: la comparada la acompana (si se sincroniza)."""
        compare = self.compare
        if self.compare_tab is None or compare is None or not compare.sync.get():
            return
        if page < compare.view.page_count and page != compare.view.current_page:
            compare.view.go_to(page)

    def _on_compare_page(self: ViewerPage, page: int) -> None:
        compare = self.compare
        if compare is None or not compare.sync.get() or self.session is None:
            return
        if page < self.view.page_count and page != self.view.current_page:
            self.view.go_to(page)

    def _on_compared_changed(self: ViewerPage, change: DocumentChange) -> None:
        if self.compare is None:
            return
        self.compare.view.refresh(None if change.kind == STRUCTURE else set(change.pages or ()))

    # * Imprimir ----------------------------------------------------------------

    def print_document(self: ViewerPage) -> None:
        """Dialogo de impresion de Windows con el documento tal como se ve (con los cambios)."""
        session, tab = self.session, self.tab
        if session is None or tab is None:
            return
        if not printing.is_available():
            self.app.show_error(core.OutputError(tr("La impresión solo está disponible en Windows.")))
            return
        status = self.app.status_bar

        def progress(done: int, total: int) -> None:
            status.set_busy(tr("Imprimiendo página {n} de {total}", n=done, total=total), 0)
            self.update_idletasks()

        try:
            owner = int(self.app.root.wm_frame(), 16)
        except (ValueError, tk.TclError):
            owner = 0
        self.log("Impresion: abriendo el dialogo", archivo=tab.path.name)
        try:
            printed = printing.print_document(session.document, tab.path.name, owner, progress)
        except core.PdfManagementError as error:
            status.set_idle()
            self.app.show_error(error)
            return
        status.set_idle()
        if printed is None:
            self.log_debug("Impresion cancelada")
            return
        self.selection_label.configure(
            text=trn("Se envió {count} página a la impresora", "Se enviaron {count} páginas a la impresora", printed)
        )
        self.log("Impresion enviada", paginas=printed, archivo=tab.path.name)

    # * Firmas digitales ---------------------------------------------------------

    def document_shown(self: ViewerPage) -> None:
        """Cambio el documento a la vista (otra pestana o guardado): las firmas se verifican de nuevo."""
        self._verified_path = None
        set_enabled(self.print_button, self.session is not None)
        if self._side_panels.get(self.side_tabs.get()) is self.signatures:
            self.refresh_signatures()

    def refresh_signatures(self: ViewerPage, force: bool = False) -> None:
        """Verifica (en segundo plano) las firmas del archivo de la pestana activa."""
        tab = self.tab
        panel = self.signatures
        if tab is None:
            panel.show_message(tr("Abra un PDF para ver sus firmas digitales."))
            return
        path = tab.path
        if not force and self._verified_path == path:
            return
        self._verified_path = path
        if not tab.session.has_signatures():
            panel.show_reports([])
            return
        panel.show_message(tr("Verificando firmas..."))
        password = tab.session.password
        note = (
            tr("Se verifica el archivo guardado; los cambios sin guardar no se incluyen.")
            if tab.session.modified
            else ""
        )

        def done(reports) -> None:
            if self.tab is tab:
                panel.show_reports(reports, note)
                self.log("Firmas verificadas", archivo=path.name, firmas=len(reports))

        def failed(error: BaseException) -> None:
            if self.tab is tab:
                panel.show_message(str(error))

        self.app.runner.submit(tr("Verificando firmas"), lambda: verify_signatures(path, password), done, failed)

    def sign_from_viewer(self: ViewerPage) -> None:
        """Firmar digitalmente: envia el documento a la seccion Firmar."""
        self._send_to("Firmar")
