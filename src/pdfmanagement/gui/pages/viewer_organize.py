# mypy: disable-error-code="misc"
# (self anotado como ViewerPage, su subclase: mypy lo marca, pero comprueba igual los atributos)
"""
Organizar paginas, deshacer/rehacer, avisos de cambios, modo edicion y menu contextual.

Parte de ``ViewerPage`` (ver ``viewer.py``): los metodos anotan ``self`` con
``ViewerPage`` para que mypy compruebe los atributos que usan.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

from ... import core
from ...core.editing import CONTENT, STRUCTURE, DocumentChange, DocumentSession
from .. import style

if TYPE_CHECKING:
    from .viewer import ViewerPage
    from .viewer_tabs import DocumentTab


class OrganizeMixin:
    """Organizar paginas, deshacer/rehacer, avisos de cambios, modo edicion y menu contextual."""

    def rotate_pages(self: ViewerPage, angle: int, pages: list[int] | None = None) -> bool:
        pages = pages or self.thumbnails.selection()
        return self._edit(lambda session: session.rotate(pages, angle), select=pages, page=self.view.current_page)

    def delete_pages(self: ViewerPage, pages: list[int] | None = None) -> bool:
        if self.session is None:
            return False
        pages = pages or self.thumbnails.selection()
        if len(pages) > 1 and not messagebox.askyesno(
            "Eliminar paginas",
            f"Se eliminaran {len(pages)} paginas. Puede deshacerlo con Ctrl+Z.\n\nContinuar?",
            parent=self,
        ):
            self.log_debug("Eliminar paginas cancelado", paginas=len(pages))
            return False
        after = max(0, min(min(pages), self.session.page_count - len(pages) - 1))
        return self._edit(lambda session: session.delete(pages), select=[after], page=after)

    def _move_dragged_pages(self: ViewerPage, pages: list[int], target: int) -> None:
        self.move_pages(pages, target)

    def move_pages(self: ViewerPage, pages: list[int], target: int) -> bool:
        """Mueve ``pages`` delante de la pagina que hoy esta en ``target`` (arrastre de miniaturas)."""
        moved: list[int] = []
        return self._edit(
            lambda session: moved.extend(session.move(pages, target)), select=lambda: moved, page=lambda: moved[0]
        )

    def insert_pdf(self: ViewerPage, at: int | None = None) -> bool:
        """Pide un PDF y lo inserta despues de la seleccion (o antes de ``at``)."""
        if self.session is None:
            return False
        chosen = filedialog.askopenfilename(title="Insertar PDF", filetypes=(("Archivos PDF", "*.pdf"),))
        if not chosen:
            self.log_debug("Insertar PDF: dialogo cancelado")
            return False
        return self.insert_pdf_file(Path(chosen), at)

    def insert_pdf_file(self: ViewerPage, source: Path, at: int | None = None) -> bool:
        if self.session is None:
            return False
        at = self._insert_position() if at is None else at
        password = self._ask_password_until_valid(Path(source))
        if password is False or password is True:
            return False
        count: list[int] = []
        return self._edit(
            lambda session: count.append(session.insert_pdf(source, at, password)),
            select=lambda: list(range(at, at + count[0])),
            page=at,
        )

    def insert_blank(self: ViewerPage, at: int | None = None) -> bool:
        if self.session is None:
            return False
        at = self._insert_position() if at is None else at
        return self._edit(lambda session: session.insert_blank(at), select=[at], page=at)

    def undo(self: ViewerPage) -> None:
        self._step_history(redo=False)

    def redo(self: ViewerPage) -> None:
        self._step_history(redo=True)

    def _step_history(self: ViewerPage, redo: bool) -> None:
        session = self.session
        if session is None or not (session.history.can_redo if redo else session.history.can_undo):
            return
        label = session.redo() if redo else session.undo()  # el aviso de cambios redibuja
        page = min(self.view.current_page, session.page_count - 1)
        self._focus([page], page)
        verb = "Rehecho" if redo else "Deshecho"
        self.selection_label.configure(text=f"{verb}: {label}")
        self.log("%s: %s", verb, label, archivo=session.name, paginas=session.page_count)

    def _insert_position(self: ViewerPage) -> int:
        return max(self.thumbnails.selection()) + 1

    def _edit(self: ViewerPage, operation: Callable[[DocumentSession], object], *, select, page) -> bool:
        """
        Ejecuta una edicion de paginas y actualiza la vista. ``select`` y
        ``page`` pueden ser valores o funciones evaluadas despues de editar.
        """
        session = self.session
        if session is None or not self._confirm_signed_edit():
            return False
        steps = session.history.undo_depth
        try:
            operation(session)
        except core.PdfManagementError as error:
            self.app.show_error(error)
            return False
        if session.history.undo_depth == steps:
            return False  # nada cambio (p. ej. soltar las paginas en su mismo lugar)
        selected = select() if callable(select) else select
        self._focus(selected, page() if callable(page) else page)  # el aviso de cambios ya redibujo
        label = session.history.undo_label
        self.selection_label.configure(text=f"{label}  ·  Ctrl+Z para deshacer")
        self.log("Edicion: %s", label, archivo=session.name, paginas=session.page_count)
        return True

    def _on_document_changed(self: ViewerPage, tab: DocumentTab, change: DocumentChange) -> None:
        """
        Unico lugar que actualiza la vista cuando cambia un documento (lo avisa
        ``DocumentSession``): visor, miniaturas, marcadores, busqueda,
        anotaciones, estado del archivo y titulo de su pestana.
        """
        if tab is not self.tab:  # pestana en segundo plano: solo su titulo (punto de cambios)
            if tab in self.tabs:
                self.tab_bar.update_tab(self.tabs.index(tab), self._tab_info(tab))
            return
        if change.kind == STRUCTURE:
            self.view.refresh()
            self.thumbnails.rebuild(keep_scroll=True)
            self.thumbnails.set_selection([page for page in self.thumbnails.selected if page < tab.session.page_count])
            self.outline.set_entries(tab.session.table_of_contents())
            self.search.invalidate()
            self.text_tool.clear(self.view)
            self.annotations.reset()
        elif change.kind == CONTENT:
            self.view.refresh(set(change.pages))
            self.thumbnails.refresh_pages(change.pages)
            self.annotations.content_changed(change.pages)
        self._refresh_file_state()

    def _focus(self: ViewerPage, select: list[int], page: int | None) -> None:
        """Tras una edicion: pagina a mostrar y miniaturas seleccionadas."""
        if page is not None and page != self.view.current_page:
            self.view.go_to(page)
        self.thumbnails.set_selection(select, anchor=select[0] if select else None)

    def _confirm_signed_edit(self: ViewerPage) -> bool:
        """Editar un PDF con firmas digitales las invalida: se avisa una vez por documento."""
        if self._signatures_confirmed or self.session is None or not self.session.has_signatures():
            return True
        confirmed = messagebox.askyesno(
            "Documento firmado",
            "Este PDF tiene firmas digitales. Cualquier cambio en las paginas hara que las firmas "
            "dejen de ser validas en la copia que guarde (el original no se modifica).\n\nDesea continuar?",
            icon="warning",
            parent=self,
        )
        self.log("Aviso de firmas digitales: %s", "continuar" if confirmed else "cancelado", archivo=self.session.name)
        self._signatures_confirmed = confirmed
        return confirmed

    def _on_delete_key(self: ViewerPage) -> None:
        """Supr elimina la anotacion seleccionada; si no hay, las paginas seleccionadas."""
        if not self.annotations.delete_selected():
            self.delete_pages()

    def toggle_edit_mode(self: ViewerPage) -> None:
        self.set_edit_mode(not self.edit_mode)

    def set_edit_mode(self: ViewerPage, enabled: bool) -> None:
        """
        Modo edicion: muestra la barra de anotacion y la de organizar paginas
        y permite reordenar arrastrando miniaturas. Fuera de el, el visor es
        solo para leer (menos botones y sin cambios accidentales).
        """
        if enabled == self.edit_mode:
            return
        self.edit_mode = enabled
        if enabled:
            self.annotations.bar.grid()
            self.page_tools.pack(fill="x", padx=6, pady=(0, 2), before=self.pages_hint)
        else:
            self.annotations.cancel_tool()
            self.annotations.select(None)
            self.annotations.bar.grid_remove()
            self.page_tools.pack_forget()
        self.thumbnails.on_move = self._move_dragged_pages if enabled else None
        accent = style.accent_color()
        self.edit_button.configure(
            text="Listo" if enabled else "Editar",
            fg_color=accent if enabled else "transparent",
            hover_color=style.accent_hover_color() if enabled else style.HOVER,
            text_color=style.WHITE if enabled else style.TEXT,
        )
        self._on_pages_selected(sorted(self.thumbnails.selected))
        self.log("Modo edicion %s", "activado" if enabled else "desactivado")

    def _on_view_right_click(self: ViewerPage, event) -> None:
        hit = self.view.event_to_page(event)
        if hit is None or self.session is None:
            return
        if hit.page not in self.thumbnails.selected:
            self.thumbnails.set_selection([hit.page], anchor=hit.page)
        annotation = self.annotations.hit(hit)
        if annotation is not None:
            self.annotations.select(annotation)
        self._show_page_menu(hit.page, event, from_view=True, annotation=annotation)

    def _page_menu(self: ViewerPage, from_view: bool = False, annotation=None) -> tk.Menu:
        """Menu de las paginas seleccionadas (miniaturas o clic derecho en el visor)."""
        pages = self.thumbnails.selection()
        subject = f"pagina {pages[0] + 1}" if len(pages) == 1 else f"{len(pages)} paginas"
        menu = tk.Menu(self, tearoff=0)
        if annotation is not None:
            self.annotations.add_menu_items(menu, annotation)
        if from_view and self.text_tool.selected_text():
            menu.add_command(label="Copiar texto", accelerator="Ctrl+C", command=self.copy_selection)
            menu.add_separator()
        menu.add_command(
            label=f"Rotar {subject} a la derecha", accelerator="Ctrl+R", command=lambda: self.rotate_pages(90, pages)
        )
        menu.add_command(
            label=f"Rotar {subject} a la izquierda",
            accelerator="Ctrl+Mayus+R",
            command=lambda: self.rotate_pages(-90, pages),
        )
        menu.add_command(label=f"Eliminar {subject}", accelerator="Supr", command=lambda: self.delete_pages(pages))
        menu.add_separator()
        menu.add_command(label="Insertar PDF antes...", command=lambda: self.insert_pdf(min(pages)))
        menu.add_command(label="Insertar PDF despues...", command=lambda: self.insert_pdf(max(pages) + 1))
        menu.add_command(label="Insertar pagina en blanco despues", command=lambda: self.insert_blank(max(pages) + 1))
        return menu

    def _show_page_menu(self: ViewerPage, page: int, event, from_view: bool = False, annotation=None) -> None:
        if self.session is None:
            return
        menu = self._page_menu(from_view, annotation)
        self.log_debug("Menu de paginas abierto", pagina=page + 1, origen="visor" if from_view else "miniaturas")
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
