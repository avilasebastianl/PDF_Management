"""
Pagina "Visor": leer, buscar y copiar texto de cualquier PDF.

Es la primera seccion de la aplicacion y el punto de partida para las
herramientas de edicion: desde aqui el documento se puede enviar a Unir,
Extraer, Firmar o Proteger.

Atajos (con la seccion visible): Ctrl+O abrir, Ctrl+F buscar, F3 / Mayus+F3
resultado siguiente / anterior, Ctrl+C copiar seleccion, Ctrl+A seleccionar la
pagina, Ctrl + / Ctrl - zoom, Ctrl+0 ajustar al ancho, Esc limpiar.
"""

from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from ... import core, recent
from ...core.editing import DocumentSession
from .. import style
from ..dialogs import DocumentPropertiesWindow, ask_password
from ..dropdown import dropdown_menu, set_dropdown_values
from ..viewer import FIT_WIDTH, HandTool, PageView, TextSelectTool, ThumbnailStrip, ViewerToolbar
from ..viewer.panels import OutlinePanel, SearchPanel
from ..widgets import format_size, icon_button, muted_label, primary_button, secondary_button, set_enabled
from .base import BasePage

SIDE_TABS = ("Miniaturas", "Marcadores", "Buscar")
TOOLS = ("Seleccionar texto", "Mano")
SEND_TARGETS = ("Unir", "Extraer", "Firmar", "Proteger")
RECENT_PLACEHOLDER = "Recientes"
SEND_PLACEHOLDER = "Enviar a..."
PLACEHOLDER = (
    "Haga clic aqui o arrastre un PDF para abrirlo",
    "Tambien puede usar el boton \"Abrir\" o Ctrl+O. Lea, busque (Ctrl+F) y copie texto.",
)


class ViewerPage(BasePage):
    name = "Visor"
    title = "Visor de PDF"
    subtitle = "Lea, busque y copie texto de cualquier PDF. Desde aqui puede enviarlo a las demas herramientas."
    icon_name = "pdf"
    scrollable = False

    def build(self) -> None:
        self.session: DocumentSession | None = None
        self._recent: list[Path] = recent.load_recent()
        self.body.grid_columnconfigure(1, weight=1)
        self.body.grid_rowconfigure(1, weight=1)
        self._build_file_bar()
        self._build_side_panel()
        self._build_viewer()
        self._bind_shortcuts()
        self._refresh_file_state()

    # * Construccion ----------------------------------------------------------

    def _build_file_bar(self) -> None:
        bar = ctk.CTkFrame(self.body, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, style.GAP))
        bar.grid_columnconfigure(2, weight=1)
        primary_button(bar, "Abrir", self.browse, "folder", width=110).grid(row=0, column=0)
        self.recent_menu = dropdown_menu(bar, self._recent_labels(), self._open_recent, width=190, height=34,
                                         max_visible=10)
        self.recent_menu.set(RECENT_PLACEHOLDER)
        self.recent_menu.grid(row=0, column=1, padx=(8, 12))
        info = ctk.CTkFrame(bar, fg_color="transparent")
        info.grid(row=0, column=2, sticky="ew")
        self.file_label = ctk.CTkLabel(info, text="", font=style.fonts().body_bold, anchor="w")
        self.file_label.pack(anchor="w")
        self.file_info = muted_label(info)
        self.file_info.pack(anchor="w")
        self.send_menu = dropdown_menu(bar, list(SEND_TARGETS), self._send_to, width=150, height=34)
        self.send_menu.set(SEND_PLACEHOLDER)
        self.send_menu.grid(row=0, column=3, padx=(8, 8))
        self.properties_button = secondary_button(bar, "Propiedades", self.show_properties, "info", width=130)
        self.properties_button.grid(row=0, column=4)

    def _build_side_panel(self) -> None:
        self.side = ctk.CTkFrame(self.body, corner_radius=style.CORNER, fg_color=style.CARD_BG,
                                 border_width=1, border_color=style.CARD_BORDER, width=250)
        self.side.grid(row=1, column=0, sticky="nsw", padx=(0, style.GAP), pady=(0, style.PAD))
        self.side.grid_propagate(False)
        self.side.pack_propagate(False)
        self.side_tabs = ctk.CTkSegmentedButton(self.side, values=list(SIDE_TABS), command=self._show_side,
                                                font=style.fonts().small)
        self.side_tabs.set(SIDE_TABS[0])
        self.side_tabs.pack(fill="x", padx=8, pady=8)
        self.side_stack = ctk.CTkFrame(self.side, fg_color="transparent")
        self.side_stack.pack(fill="both", expand=True, padx=2, pady=(0, 8))
        self.side_visible = True

    def _build_viewer(self) -> None:
        card = ctk.CTkFrame(self.body, corner_radius=style.CORNER, fg_color=style.CARD_BG,
                            border_width=1, border_color=style.CARD_BORDER)
        card.grid(row=1, column=1, sticky="nsew", pady=(0, style.PAD))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)

        self.view = PageView(card, continuous=True, placeholder=PLACEHOLDER, on_empty_click=self.browse,
                             on_drop=self._on_drop)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 6))
        icon_button(top, "list", self.toggle_side_panel, "Mostrar u ocultar el panel lateral").pack(side="left", padx=(0, 6))
        self.toolbar = ViewerToolbar(top, self.view)
        self.toolbar.pack(side="left", fill="x", expand=True)
        self.tool_selector = ctk.CTkSegmentedButton(top, values=list(TOOLS), command=self._choose_tool,
                                                    font=style.fonts().small)
        self.tool_selector.set(TOOLS[0])
        self.tool_selector.pack(side="left", padx=(10, 6))
        self.search_button = icon_button(top, "zoom_in", self.open_search, "Buscar (Ctrl+F)")
        self.search_button.pack(side="left")
        ctk.CTkFrame(card, height=1, corner_radius=0, fg_color=style.CARD_BORDER).grid(row=1, column=0, sticky="ew", padx=1)
        self.view.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        self.selection_label = muted_label(card, "")
        self.selection_label.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 6))

        self.text_tool = TextSelectTool(self._words_for, on_change=self._on_selection_changed)
        self.hand_tool = HandTool()
        self.view.set_tool(self.text_tool)

        self.thumbnails = ThumbnailStrip(self.side_stack, self.view)
        self.outline = OutlinePanel(self.side_stack, self.view)
        self.search = SearchPanel(self.side_stack, self.view)
        self._side_panels = dict(zip(SIDE_TABS, (self.thumbnails, self.outline, self.search)))
        self._show_side(SIDE_TABS[0], log=False)

    def _bind_shortcuts(self) -> None:
        root = self.app.root
        bindings = {
            "<Control-o>": self.browse,
            "<Control-f>": self.open_search,
            "<F3>": lambda: self.search.next(),
            "<Shift-F3>": lambda: self.search.previous(),
            "<Control-c>": self.copy_selection,
            "<Control-a>": self.select_page,
            "<Escape>": self.clear_marks,
            "<Control-plus>": lambda: self.view.zoom_in(),
            "<Control-equal>": lambda: self.view.zoom_in(),
            "<Control-minus>": lambda: self.view.zoom_out(),
            "<Control-Key-0>": lambda: self.view.set_zoom(FIT_WIDTH),
        }
        for sequence, action in bindings.items():
            root.bind(sequence, lambda event, run=action: self._shortcut(event, run), add="+")

    def _shortcut(self, event, action) -> str | None:
        """Atajos activos solo con el Visor a la vista y sin un campo de texto enfocado."""
        if self.app.current_page != self.name:
            return None
        focused = self.focus_get()
        if event.keysym.lower() in ("c", "a") and focused is not None and focused.winfo_class() in ("Entry", "Text"):
            return None  # copiar / seleccionar dentro del campo, como siempre
        action()
        return "break"

    # * Abrir ---------------------------------------------------------------

    def browse(self) -> None:
        chosen = filedialog.askopenfilename(title="Abrir PDF", filetypes=(("Archivos PDF", "*.pdf"),))
        if chosen:
            self.open_file(Path(chosen), source="dialogo")
        else:
            self.log_debug("Abrir: dialogo cancelado")

    def receive_file(self, path: Path) -> None:
        self.open_file(path, source="enviado desde otra seccion")

    def _on_drop(self, files: list) -> None:
        if files:
            self.open_file(Path(files[0]), source="arrastrado")

    def _open_recent(self, label: str) -> None:
        self.recent_menu.set(RECENT_PLACEHOLDER)
        labels = self._recent_labels()
        if label in labels and self._recent:
            self.open_file(self._recent[labels.index(label)], source="recientes")

    def open_file(self, path: Path, source: str = "dialogo") -> bool:
        """Abre ``path`` en el visor (pide la contrasena si hace falta)."""
        path = Path(path)
        password, retry = None, False
        while True:
            try:
                session = DocumentSession.open(path, password)
                break
            except core.PasswordRequiredError as error:
                self.log("%s pide contrasena%s", path.name, " (la anterior no era correcta)" if retry else "")
                password = ask_password(self, path.name, retry=retry or isinstance(error, core.WrongPasswordError))
                retry = True
                if not password:
                    self.log("Apertura cancelada: no se ingreso la contrasena", archivo=path.name)
                    return False
            except core.PdfManagementError as error:
                self.app.show_error(error)
                return False
        self._close_session()
        self.session = session
        self.view.set_document(session.document)
        self.thumbnails.rebuild()
        self.outline.set_entries(session.table_of_contents())
        self.search.set_document(session.document)
        self.text_tool.clear(self.view)
        self._recent = recent.add_recent(session.path)
        set_dropdown_values(self.recent_menu, self._recent_labels())
        self.recent_menu.set(RECENT_PLACEHOLDER)
        self._refresh_file_state()
        self.log(
            "Documento abierto: %s", session.name, origen=source, paginas=session.page_count,
            protegido=session.encrypted, firmas_digitales=session.has_signatures(),
            marcadores=len(session.table_of_contents()),
        )
        return True

    def _close_session(self) -> None:
        if self.session is not None:
            self.search.set_document(None)
            self.view.set_document(None)
            self.session.close()
            self.session = None

    def on_close(self) -> None:
        self._close_session()

    # * Acciones --------------------------------------------------------------

    def show_properties(self) -> None:
        if self.session is None:
            return
        self.log("Propiedades abiertas", archivo=self.session.name)
        size = self.view.sizes[self.view.current_page] if self.view.sizes else None
        DocumentPropertiesWindow(self, self.session.properties(), size)

    def _send_to(self, target: str) -> None:
        self.send_menu.set(SEND_PLACEHOLDER)
        if self.session is None:
            return
        self.log("Documento enviado a %s", target, archivo=self.session.name)
        self.app.open_in(target, self.session.path)

    def open_search(self) -> None:
        if not self.side_visible:
            self.toggle_side_panel()
        self.side_tabs.set("Buscar")
        self._show_side("Buscar")
        self.search.focus_entry()

    def copy_selection(self) -> None:
        text = self.text_tool.selected_text()
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.selection_label.configure(text=f"Copiado al portapapeles: {len(text)} caracteres")
        self.log("Texto copiado", caracteres=len(text), pagina=self.view.current_page + 1)

    def select_page(self) -> None:
        if self.session is not None:
            self.tool_selector.set(TOOLS[0])
            self._choose_tool(TOOLS[0], log=False)
            self.text_tool.select_all(self.view, self.view.current_page)

    def clear_marks(self) -> None:
        self.text_tool.clear(self.view)
        self.search.clear()

    def toggle_side_panel(self) -> None:
        self.side_visible = not self.side_visible
        if self.side_visible:
            self.side.grid()
        else:
            self.side.grid_remove()
        self.log_debug("Panel lateral %s", "visible" if self.side_visible else "oculto")

    def _show_side(self, name: str, log: bool = True) -> None:
        for panel_name, panel in self._side_panels.items():
            if panel_name == name:
                panel.pack(fill="both", expand=True)
            else:
                panel.pack_forget()
        if log:
            self.log_debug("Panel lateral: %s", name)

    def _choose_tool(self, name: str, log: bool = True) -> None:
        self.view.set_tool(self.text_tool if name == TOOLS[0] else self.hand_tool)
        if log:
            self.log("Herramienta: %s", name)

    # * Estado --------------------------------------------------------------

    def _words_for(self, page: int) -> list[tuple]:
        return self.session.words(page) if self.session is not None else []

    def _on_selection_changed(self, words: int) -> None:
        self.selection_label.configure(text=f"{words} palabras seleccionadas · Ctrl+C para copiar" if words else "")

    def _refresh_file_state(self) -> None:
        session = self.session
        if session is None:
            self.file_label.configure(text="Ningun documento abierto")
            self.file_info.configure(text="Abra un PDF con el boton, con Ctrl+O o arrastrandolo al visor.")
        else:
            details = [f"{session.page_count} paginas", format_size(session.path.stat().st_size)]
            if session.encrypted:
                details.append("protegido")
            if session.has_signatures():
                details.append("con firmas digitales")
            self.file_label.configure(text=session.name)
            self.file_info.configure(text="  ·  ".join(details) + f"  ·  {session.path.parent}")
        state = "normal" if session is not None else "disabled"
        for widget in (self.send_menu, self.properties_button):
            if widget.cget("state") != state:  # evitar redibujos innecesarios
                widget.configure(state=state)
        set_enabled(self.search_button, session is not None)

    def _recent_labels(self) -> list[str]:
        labels = [entry.name for entry in self._recent]
        seen: dict[str, int] = {}
        for index, label in enumerate(labels):  # nombres repetidos: se agrega la carpeta
            if label in seen:
                labels[index] = f"{label}  ({self._recent[index].parent.name})"
            seen[label] = index
        return labels or ["(sin recientes)"]
