"""
Pagina "Organizar": reordenar, girar, eliminar e insertar paginas de un PDF
en una cuadricula de miniaturas grandes.

Usa la misma ``DocumentSession`` que el Visor: cada cambio se puede deshacer
y el resultado se guarda siempre con "Guardar como" (el original no se toca).
"""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ... import core
from ...core.editing import DocumentSession
from ...i18n import tr, trn
from .. import style
from ..dialogs import ask_password
from ..popup_menu import PopupMenu
from ..viewer.page_grid import PageGrid
from ..widgets import ToolTip, icon_button, muted_label, primary_button, secondary_button, set_enabled
from .base import BasePage

HINT = tr("Arrastre las páginas para cambiar el orden  ·  Clic para seleccionar (Ctrl o Mayús: varias)  ·  + inserta")
# Teclas que dentro de un campo de texto conservan su funcion normal.
TEXT_FIELD_KEYS = {"a", "z", "y", "delete"}


class OrganizePage(BasePage):
    name = "Organizar"  # identificador de la seccion (no se traduce)
    title = tr("Organizar páginas")
    subtitle = tr("Reordene, gire, elimine o inserte páginas arrastrando las miniaturas.")
    icon_name = "pages_tab"
    scrollable = False

    def build(self) -> None:
        self.session: DocumentSession | None = None
        self.saved_path: Path | None = None
        self.body.grid_rowconfigure(2, weight=1)
        self._build_toolbar()
        self.hint = muted_label(self.body, HINT, anchor="w")
        self.hint.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        card = ctk.CTkFrame(
            self.body,
            corner_radius=style.CORNER,
            fg_color=style.CARD_BG,
            border_width=1,
            border_color=style.CARD_BORDER,
        )
        card.grid(row=2, column=0, sticky="nsew", pady=(0, style.COMPACT_PAD))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)
        self.grid_view = PageGrid(
            card,
            on_rotate=self.rotate,
            on_delete=self.delete,
            on_move=self.move,
            on_insert=self._show_insert_menu,
            on_selection=self._on_selection,
            on_empty_click=self.browse,
            on_drop=self._on_drop,
        )
        self.grid_view.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        self.grid_view.on_hint = self._show_hint
        self._bind_shortcuts()
        self._refresh_state()

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self.body, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, style.GAP))
        bar.grid_columnconfigure(2, weight=1)
        primary_button(bar, tr("Abrir PDF"), self.browse, "folder", width=130).grid(row=0, column=0)
        self.close_button = secondary_button(bar, tr("Cerrar"), self.close_document, "clear", width=100, height=38)
        self.close_button.grid(row=0, column=1, padx=(8, 0))
        ToolTip(self.close_button, tr("Cerrar el archivo (si tiene cambios sin guardar, pregunta antes)"))
        info = ctk.CTkFrame(bar, fg_color="transparent")
        info.grid(row=0, column=2, sticky="ew", padx=12)
        self.file_label = ctk.CTkLabel(info, text="", font=style.fonts().body_bold, anchor="w")
        self.file_label.pack(anchor="w")
        self.file_info = muted_label(info)
        self.file_info.pack(anchor="w")
        actions = ctk.CTkFrame(bar, fg_color="transparent")
        actions.grid(row=0, column=3, padx=(0, 8))
        self.undo_button = icon_button(actions, "undo", self.undo, tr("Deshacer (Ctrl+Z)"), size=34)
        self.redo_button = icon_button(actions, "redo", self.redo, tr("Rehacer (Ctrl+Y)"), size=34)
        separator = ctk.CTkFrame(actions, width=1, height=24, fg_color=style.CARD_BORDER)
        self.select_all_button = icon_button(
            actions, "check", self.toggle_select_all, tr("Seleccionar todas (Ctrl+A)"), size=34
        )
        self.rotate_left_button = icon_button(
            actions,
            "rotate_left",
            lambda: self.rotate(self.grid_view.selection(), -90),
            tr("Girar las seleccionadas a la izquierda"),
            size=34,
        )
        self.rotate_right_button = icon_button(
            actions,
            "rotate_right",
            lambda: self.rotate(self.grid_view.selection(), 90),
            tr("Girar las seleccionadas a la derecha"),
            size=34,
        )
        self.delete_button = icon_button(
            actions,
            "delete",
            lambda: self.delete(self.grid_view.selection()),
            tr("Eliminar las seleccionadas (Supr)"),
            size=34,
        )
        for widget in (self.undo_button, self.redo_button):
            widget.pack(side="left", padx=1)
        separator.pack(side="left", padx=8)
        for widget in (self.select_all_button, self.rotate_left_button, self.rotate_right_button, self.delete_button):
            widget.pack(side="left", padx=1)
        self.discard_button = secondary_button(bar, tr("Descartar cambios"), self.discard_changes, "refresh", width=170)
        self.discard_button.grid(row=0, column=4, padx=(0, 8))
        ToolTip(self.discard_button, tr("Vuelve al archivo como estaba al abrirlo (Ctrl+Y recupera los cambios)"))
        self.save_button = secondary_button(bar, tr("Guardar como"), self.save_as, "save_as", width=140)
        self.save_button.grid(row=0, column=5)

    def _bind_shortcuts(self) -> None:
        bindings = {
            "<Delete>": lambda: self.delete(self.grid_view.selection()),
            "<Control-a>": self.toggle_select_all,
            "<Control-z>": self.undo,
            "<Control-y>": self.redo,
            "<Control-Z>": self.redo,
            "<Control-s>": self.save_as,
            "<Control-S>": self.save_as,
        }
        for sequence, action in bindings.items():
            self.app.root.bind(sequence, lambda event, run=action: self._shortcut(event, run), add="+")

    def _shortcut(self, event, action) -> str | None:
        """Solo con esta seccion a la vista y sin un campo de texto enfocado."""
        if self.app.current_page != self.name:
            return None
        focused = self.focus_get()
        if (
            event.keysym.lower() in TEXT_FIELD_KEYS
            and focused is not None
            and focused.winfo_class() in ("Entry", "Text")
        ):
            return None
        action()
        return "break"

    # * Abrir ----------------------------------------------------------------------

    def browse(self) -> None:
        chosen = filedialog.askopenfilename(title=tr("Abrir PDF"), filetypes=((tr("Archivos PDF"), "*.pdf"),))
        if chosen:
            self.open_file(Path(chosen))

    def receive_file(self, path: Path) -> None:
        self.log("Archivo recibido de otra seccion: %s", path.name)
        self.open_file(path)

    def _on_drop(self, paths: list) -> None:
        pdfs = [Path(path) for path in paths if str(path).lower().endswith(".pdf")]
        if pdfs:
            self.open_file(pdfs[0])

    def open_file(self, path: Path) -> bool:
        if not self._confirm_discard():
            return False
        password = None
        retry = False
        while True:
            try:
                session = DocumentSession.open(path, password)
                break
            except core.PasswordRequiredError as error:
                password = ask_password(self, path.name, retry=retry or isinstance(error, core.WrongPasswordError))
                retry = True
                if not password:
                    return False
            except core.PdfManagementError as error:
                self.app.show_error(error)
                return False
        self._close_session()
        self.session, self.saved_path = session, None
        session.changes.subscribe(lambda _change: self._refresh_state())
        self.grid_view.set_document(session.document)
        self._refresh_state()
        self.log("Documento para organizar: %s", session.name, paginas=session.page_count)
        return True

    # * Acciones ---------------------------------------------------------------------

    def rotate(self, pages: list[int], angle: int) -> None:
        if self.session is None or not pages:
            return
        self._edit(lambda session: session.rotate(pages, angle), select=pages)

    def delete(self, pages: list[int]) -> None:
        if self.session is None or not pages:
            return
        self._edit(lambda session: session.delete(pages), select=[])

    def move(self, pages: list[int], target: int) -> None:
        if self.session is None or not pages:
            return
        moved: list[int] = []
        self._edit(lambda session: moved.extend(session.move(pages, target)), select=moved)

    def insert_blank(self, at: int) -> None:
        if self.session is not None:
            self._edit(lambda session: session.insert_blank(at), select=[at])

    def insert_pdf(self, at: int) -> None:
        if self.session is None:
            return
        chosen = filedialog.askopenfilename(title=tr("Insertar PDF"), filetypes=((tr("Archivos PDF"), "*.pdf"),))
        if not chosen:
            return
        path, password, retry = Path(chosen), None, False
        while True:
            try:
                count = self.session.insert_pdf(path, at, password)
                break
            except core.PasswordRequiredError as error:
                password = ask_password(self, path.name, retry=retry or isinstance(error, core.WrongPasswordError))
                retry = True
                if not password:
                    return
            except core.PdfManagementError as error:
                self.app.show_error(error)
                return
        self.grid_view.refresh(select=list(range(at, at + count)))
        self.log("PDF insertado: %s", path.name, posicion=at + 1, paginas=count)

    def _show_insert_menu(self, at: int, x: int, y: int) -> None:
        menu = PopupMenu(self.grid_view.canvas)
        menu.add_command(label=tr("Página en blanco"), command=lambda: self.insert_blank(at))
        menu.add_command(label=tr("Páginas de otro PDF..."), command=lambda: self.insert_pdf(at))
        menu.tk_popup(x, y)

    def _edit(self, operation, select: list[int]) -> None:
        session = self.session
        if session is None:
            return
        try:
            operation(session)
        except core.PdfManagementError as error:
            self.app.show_error(error)
            return
        self.grid_view.refresh(select=select)
        self.log("Organizar: %s", session.history.undo_label or "", paginas=session.page_count)

    def undo(self) -> None:
        if self.session is not None and self.session.undo():
            self.grid_view.refresh(select=[])

    def redo(self) -> None:
        if self.session is not None and self.session.redo():
            self.grid_view.refresh(select=[])

    def discard_changes(self) -> None:
        """Deshace todo lo hecho desde que se abrio (o se guardo) el archivo."""
        session = self.session
        if session is None or not session.modified:
            return
        steps = 0
        while session.modified and session.history.can_undo:
            session.undo()
            steps += 1
        self.grid_view.refresh(select=[])
        self.hint.configure(text=tr("Cambios descartados. Ctrl+Y los recupera."))
        self.log("Cambios descartados", pasos=steps, archivo=session.name)

    def close_document(self) -> None:
        """Cierra el archivo; si tiene cambios sin guardar, pregunta (guardar, descartar o seguir)."""
        if self.session is None or not self._confirm_discard():
            return
        name = self.session.name
        self._close_session()
        self.saved_path = None
        self._refresh_state()
        self.hint.configure(text=HINT)
        self.log("Documento cerrado", archivo=name)

    def toggle_select_all(self) -> None:
        if self.session is None:
            return
        if len(self.grid_view.selected) == self.session.page_count:
            self.grid_view.set_selection([])
        else:
            self.grid_view.select_all()

    # * Guardar ----------------------------------------------------------------------

    def save_as(self) -> bool:
        session = self.session
        if session is None:
            return False
        suggested = self.saved_path or self.default_output(session.path, tr("organizado"))
        chosen = filedialog.asksaveasfilename(
            title=tr("Guardar como"),
            defaultextension=".pdf",
            filetypes=((tr("Archivos PDF"), "*.pdf"),),
            initialdir=str(suggested.parent),
            initialfile=suggested.name,
            parent=self,
        )
        if not chosen:
            return False
        try:
            saved = session.save_as(Path(chosen))
        except core.PdfManagementError as error:
            self.app.show_error(error)
            return False
        self.saved_path = saved
        self._refresh_state()
        self.log("Documento organizado guardado: %s", saved.name, paginas=session.page_count)
        self.app.notify_success(tr("Documento guardado"), saved)
        return True

    def _confirm_discard(self) -> bool:
        session = self.session
        if session is None or not session.modified:
            return True
        answer = messagebox.askyesnocancel(
            tr("Cambios sin guardar"),
            tr("{documento} tiene cambios sin guardar.", documento=session.name)
            + "\n\n"
            + tr("¿Desea guardarlos en un archivo nuevo?")
            + "\n\n"
            + tr("Sí: Guardar como...\nNo: descartar los cambios\nCancelar: seguir editando"),
            icon="warning",
            parent=self,
        )
        if answer is None:
            return False
        return self.save_as() if answer else True

    def can_close(self) -> bool:
        return self._confirm_discard()

    def on_close(self) -> None:
        self._close_session()

    def _close_session(self) -> None:
        if self.session is not None:
            self.grid_view.set_document(None)
            self.session.close()
            self.session = None

    # * Estado ------------------------------------------------------------------------

    def _on_selection(self, pages: list[int]) -> None:
        has = bool(pages)
        for button in (self.rotate_left_button, self.rotate_right_button, self.delete_button):
            set_enabled(button, has)
        if pages and not self.grid_view.hint:
            self._show_hint("")

    def _show_hint(self, text: str) -> None:
        pages = self.grid_view.selection()
        if text:
            self.hint.configure(text=text)
        elif pages:
            self.hint.configure(
                text=trn("{count} página seleccionada", "{count} páginas seleccionadas", len(pages))
                + "  ·  "
                + tr("arrastre para moverlas, Supr para eliminarlas")
            )
        else:
            self.hint.configure(text=HINT)

    def _refresh_state(self) -> None:
        session = self.session
        if session is None:
            self.file_label.configure(text=tr("Ningún documento abierto"))
            self.file_info.configure(text=tr("Abra un PDF o arrástrelo a la cuadrícula."))
        else:
            shown = self.saved_path or session.path
            details = [trn("{count} página", "{count} páginas", session.page_count)]
            if session.modified:
                details.insert(0, tr("cambios sin guardar"))
            self.file_label.configure(text=shown.name + ("  •" if session.modified else ""))
            self.file_info.configure(text="  ·  ".join(details) + f"  ·  {shown.parent}")
        has = session is not None
        set_enabled(self.undo_button, has and session is not None and session.history.can_undo)
        set_enabled(self.redo_button, has and session is not None and session.history.can_redo)
        set_enabled(self.select_all_button, has)
        self.save_button.configure(state="normal" if has else "disabled")
        self.close_button.configure(state="normal" if has else "disabled")
        modified = session is not None and session.modified
        self.discard_button.configure(state="normal" if modified else "disabled")
        self._on_selection(self.grid_view.selection())
