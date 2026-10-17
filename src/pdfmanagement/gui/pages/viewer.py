"""
Pagina "Visor": leer, buscar, copiar texto y organizar las paginas de un PDF.

Es la primera seccion de la aplicacion y el punto de partida para las
herramientas de edicion: desde aqui el documento se puede enviar a Unir,
Extraer, Firmar o Proteger.

Varios documentos a la vez en pestanas, como un navegador (``DocumentTab``):
cada una conserva su sesion, historial, pagina, zoom, desplazamiento y
seleccion. Dos modos de lectura: "toda la ventana" (Ctrl+Mayus+F; solo el
visor y las pestanas dentro de la ventana) y pantalla completa (F11).

Organizar paginas (panel Paginas, menu contextual o atajos): rotar,
eliminar, reordenar arrastrando miniaturas, insertar otro PDF o una pagina en
blanco. Anotar (barra de anotacion y panel Notas, ver viewer_annotations.py):
resaltar, subrayar, tachar, notas, texto, formas, lineas, flechas y dibujo a
mano. Todo se puede deshacer y se guarda siempre con "Guardar como": el
archivo original nunca se modifica.

Atajos (con la seccion visible): Ctrl+O abrir (en una pestana nueva), Ctrl+W
cerrar pestana, Ctrl+Tab / Ctrl+Mayus+Tab cambiar de pestana, Ctrl+Mayus+F
visor en toda la ventana, F11 pantalla completa, Ctrl+E editar, Ctrl+S / Ctrl+Mayus+S guardar
como, Ctrl+Z deshacer, Ctrl+Y / Ctrl+Mayus+Z rehacer, Ctrl+R / Ctrl+Mayus+R
rotar a la derecha / izquierda, Supr eliminar paginas, Ctrl+F buscar, F3 /
Mayus+F3 resultado siguiente / anterior, Ctrl+C copiar seleccion, Ctrl+A
seleccionar la pagina, Ctrl + / Ctrl - zoom, Ctrl+0 ajustar al ancho, Esc
terminar la herramienta de anotacion y limpiar la seleccion.
"""

import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ... import core, recent
from ...core.editing import DocumentSession
from .. import style
from ..dialogs import DocumentPropertiesWindow, ask_password
from ..dropdown import dropdown_menu, set_dropdown_values
from ..icons import icon
from ..viewer import FIT_WIDTH, HandTool, PageView, ThumbnailStrip, ViewerToolbar
from ..viewer.annotation_tools import SelectTool
from ..viewer.find_bar import FindBar
from ..viewer.panels import OutlinePanel, SearchPanel
from ..viewer.tab_strip import TabInfo, TabStrip
from ..widgets import ToolTip, format_size, icon_button, muted_label, primary_button, secondary_button, set_enabled
from .base import BasePage
from .viewer_annotations import ViewerAnnotations

SIDE_TABS = ("Paginas", "Marcadores", "Buscar", "Notas")
TOOLS = ("Texto", "Mano")
SEND_TARGETS = ("Unir", "Extraer", "Firmar", "Proteger")
RECENT_PLACEHOLDER = "Recientes"
SEND_PLACEHOLDER = "Enviar a..."
PLACEHOLDER = (
    "Haga clic aqui o arrastre un PDF para abrirlo",
    'Tambien puede usar el boton "Abrir" o Ctrl+O. Lea, busque (Ctrl+F), copie texto y organice las paginas.',
)
# Teclas que dentro de un campo de texto conservan su funcion normal.
TEXT_FIELD_KEYS = {"c", "a", "z", "y", "delete"}
MAX_TABS = 12
NORMAL, WINDOW, FULLSCREEN = "normal", "ventana", "pantalla completa"


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

    @property
    def path(self) -> Path:
        return self.saved_path or self.session.path


class ViewerPage(BasePage):
    name = "Visor"
    title = "Visor de PDF"
    subtitle = "Lea, busque, anote y organice las paginas de cualquier PDF."
    icon_name = "pdf"
    scrollable = False
    show_header = False  # el visor aprovecha todo el alto; el titulo ya lo indica el menu lateral

    def build(self) -> None:
        self.tabs: list[DocumentTab] = []
        self.active = -1  # indice de la pestana visible (-1: ninguna)
        self.view_mode = NORMAL  # NORMAL, WINDOW (toda la ventana) o FULLSCREEN
        self._recent: list[Path] = recent.load_recent()
        # Todo el espacio sobrante es para el visor (BasePage da peso a la columna 0).
        self.body.grid_columnconfigure(0, weight=0)
        self.body.grid_columnconfigure(1, weight=1)
        self.body.grid_rowconfigure(2, weight=1)
        self._build_file_bar()
        self._build_tab_bar()
        self._build_side_panel()
        self._build_viewer()
        self._bind_shortcuts()
        self._refresh_file_state()

    # * Pestana activa ---------------------------------------------------------

    @property
    def tab(self) -> DocumentTab | None:
        return self.tabs[self.active] if 0 <= self.active < len(self.tabs) else None

    @property
    def session(self) -> DocumentSession | None:
        return self.tab.session if self.tab is not None else None

    @property
    def saved_path(self) -> Path | None:
        return self.tab.saved_path if self.tab is not None else None

    @saved_path.setter
    def saved_path(self, value: Path | None) -> None:
        if self.tab is not None:
            self.tab.saved_path = value

    @property
    def _signatures_confirmed(self) -> bool:
        return self.tab.signatures_confirmed if self.tab is not None else False

    @_signatures_confirmed.setter
    def _signatures_confirmed(self, value: bool) -> None:
        if self.tab is not None:
            self.tab.signatures_confirmed = value

    # * Construccion ----------------------------------------------------------

    def _build_file_bar(self) -> None:
        bar = self.file_bar = ctk.CTkFrame(self.body, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, style.GAP))
        bar.grid_columnconfigure(2, weight=1)
        primary_button(bar, "Abrir", self.browse, "folder", width=110).grid(row=0, column=0)
        self.recent_menu = dropdown_menu(bar, self._recent_labels(), self._open_recent, width=160, height=34)
        self.recent_menu.set(RECENT_PLACEHOLDER)
        self.recent_menu.grid(row=0, column=1, padx=(8, 12))
        info = ctk.CTkFrame(bar, fg_color="transparent")
        info.grid(row=0, column=2, sticky="ew")
        self.file_label = ctk.CTkLabel(info, text="", font=style.fonts().body_bold, anchor="w")
        self.file_label.pack(anchor="w")
        self.file_info = muted_label(info)
        self.file_info.pack(anchor="w")
        history = ctk.CTkFrame(bar, fg_color="transparent")
        history.grid(row=0, column=3, padx=(8, 4))
        self.undo_button = icon_button(
            history, "undo", self.undo, lambda: self._history_tip("Deshacer", "Ctrl+Z"), size=34, state="disabled"
        )
        self.undo_button.pack(side="left")
        self.redo_button = icon_button(
            history, "redo", self.redo, lambda: self._history_tip("Rehacer", "Ctrl+Y"), size=34, state="disabled"
        )
        self.redo_button.pack(side="left", padx=(2, 0))
        self.properties_button = icon_button(
            history, "info", self.show_properties, "Propiedades del documento", size=34, state="disabled"
        )
        self.properties_button.pack(side="left", padx=(2, 0))
        self.save_button = secondary_button(bar, "Guardar como", self.save_as, "save_as", width=140)
        self.save_button.grid(row=0, column=4, padx=(4, 8))
        self.send_menu = dropdown_menu(bar, list(SEND_TARGETS), self._send_to, width=140, height=34)
        self.send_menu.set(SEND_PLACEHOLDER)
        self.send_menu.grid(row=0, column=5)

    def _build_tab_bar(self) -> None:
        """Pestanas de los documentos abiertos (se muestra con al menos uno)."""
        self.tab_bar = TabStrip(
            self.body, on_select=self.switch_to, on_close=self._close_tab_clicked, on_new=self.browse
        )
        self.tab_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        self.tab_bar.grid_remove()

    def _build_side_panel(self) -> None:
        self.side = ctk.CTkFrame(
            self.body,
            corner_radius=style.CORNER,
            fg_color=style.CARD_BG,
            border_width=1,
            border_color=style.CARD_BORDER,
            width=272,
        )
        self.side.grid(row=2, column=0, sticky="nsw", padx=(0, style.GAP), pady=(0, style.COMPACT_PAD))
        self.side.grid_propagate(False)
        self.side.pack_propagate(False)
        self.side_tabs = ctk.CTkSegmentedButton(
            self.side, values=list(SIDE_TABS), command=self._show_side, font=style.fonts().small
        )
        self.side_tabs.set(SIDE_TABS[0])
        self.side_tabs.pack(fill="x", padx=8, pady=8)
        self.side_stack = ctk.CTkFrame(self.side, fg_color="transparent")
        self.side_stack.pack(fill="both", expand=True, padx=2, pady=(0, 8))
        self.side_visible = True

    def _build_pages_panel(self) -> ctk.CTkFrame:
        """Miniaturas con la barra de organizacion encima."""
        panel = ctk.CTkFrame(self.side_stack, fg_color="transparent")
        tools = self.page_tools = ctk.CTkFrame(panel, fg_color="transparent")  # visible en modo edicion
        self.page_buttons = [
            icon_button(tools, "rotate_left", lambda: self.rotate_pages(-90), "Rotar a la izquierda (Ctrl+Mayus+R)"),
            icon_button(tools, "rotate_right", lambda: self.rotate_pages(90), "Rotar a la derecha (Ctrl+R)"),
            icon_button(tools, "delete", self.delete_pages, "Eliminar las paginas seleccionadas (Supr)"),
            icon_button(tools, "insert_pdf", self.insert_pdf, "Insertar otro PDF despues de la seleccion"),
            icon_button(
                tools, "blank_page", self.insert_blank, "Insertar una pagina en blanco despues de la seleccion"
            ),
        ]
        for button in self.page_buttons:
            button.pack(side="left", padx=(0, 2))
        self.pages_hint = muted_label(panel, "")
        self.pages_hint.pack(fill="x", padx=10, pady=(0, 4))
        self.thumbnails = ThumbnailStrip(
            panel,
            self.view,
            on_move=None,  # arrastrar reordena solo al editar
            on_context=self._show_page_menu,
            on_selection=self._on_pages_selected,
        )
        self.thumbnails.pack(fill="both", expand=True)
        return panel

    def _build_viewer(self) -> None:
        card = ctk.CTkFrame(
            self.body,
            corner_radius=style.CORNER,
            fg_color=style.CARD_BG,
            border_width=1,
            border_color=style.CARD_BORDER,
        )
        card.grid(row=2, column=1, sticky="nsew", pady=(0, style.COMPACT_PAD))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(3, weight=1)

        self.view = PageView(
            card, continuous=True, placeholder=PLACEHOLDER, on_empty_click=self.browse, on_drop=self._on_drop
        )
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 6))
        icon_button(top, "list", self.toggle_side_panel, "Mostrar u ocultar el panel lateral").pack(
            side="left", padx=(0, 6)
        )
        self.toolbar = ViewerToolbar(top, self.view)
        self.toolbar.pack(side="left", fill="x", expand=True)
        self.tool_selector = ctk.CTkSegmentedButton(
            top, values=list(TOOLS), command=self._choose_tool, font=style.fonts().small
        )
        self.tool_selector.set(TOOLS[0])
        self.tool_selector.pack(side="left", padx=(10, 6))
        tips = {TOOLS[0]: "Seleccionar y copiar texto (Ctrl+C)", TOOLS[1]: "Arrastrar para mover la pagina"}
        for value, button in self.tool_selector._buttons_dict.items():  # noqa: SLF001 (no admite bind)
            ToolTip(button, tips[value])
        self.search_button = secondary_button(top, "Buscar", self.toggle_find, "search", width=92, height=30)
        self.search_button.pack(side="left")
        ToolTip(self.search_button, "Buscar palabras en el documento (Ctrl+F)")
        self.edit_button = secondary_button(top, "Editar", self.toggle_edit_mode, "edit", width=92, height=30)
        self.edit_button.pack(side="left", padx=(6, 0))
        ToolTip(self.edit_button, "Mostrar u ocultar las herramientas para anotar y organizar paginas (Ctrl+E)")
        self.window_button = icon_button(
            top,
            "window_mode",
            self.toggle_window_mode,
            lambda: (
                "Volver a la vista normal (Ctrl+Mayus+F o Esc)"
                if self.view_mode == WINDOW
                else "Visor en toda la ventana para leer (Ctrl+Mayus+F)"
            ),
        )
        self.window_button.pack(side="left", padx=(6, 0))
        self.fullscreen_button = icon_button(
            top,
            "fullscreen",
            self.toggle_fullscreen,
            lambda: "Salir de pantalla completa (F11 o Esc)" if self.fullscreen else "Pantalla completa (F11)",
        )
        self.fullscreen_button.pack(side="left", padx=(2, 0))
        ctk.CTkFrame(card, height=1, corner_radius=0, fg_color=style.CARD_BORDER).grid(
            row=2, column=0, sticky="ew", padx=1
        )
        self.view.grid(row=3, column=0, sticky="nsew", padx=8, pady=8)
        self.view.canvas.bind("<ButtonPress-3>", self._on_view_right_click, add="+")
        self.selection_label = muted_label(card, "")
        self.selection_label.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 6))

        self.text_tool = SelectTool(
            self._words_for,
            self._on_selection_changed,
            hit_annotation=lambda hit: self.annotations.hit(hit),
            on_select=lambda info: self.annotations.select(info),
            on_move=lambda info, dx, dy: self.annotations.move(info, dx, dy),
            on_edit=lambda info: self.annotations.edit_text(info),
        )
        self.hand_tool = HandTool()
        self.view.set_tool(self.text_tool)

        self.pages_panel = self._build_pages_panel()
        self.outline = OutlinePanel(self.side_stack, self.view)
        self.search = SearchPanel(self.side_stack, self.view)
        self.annotations = ViewerAnnotations(self, card, self.side_stack)
        self.find_bar = FindBar(self.view, self.search, on_show_list=self._show_search_list, on_close=self.close_find)
        self.annotations.bar.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 6))
        self.annotations.bar.grid_remove()  # aparece con el boton Editar
        self.edit_mode = False
        panels = (self.pages_panel, self.outline, self.search, self.annotations.panel)
        self._side_panels = dict(zip(SIDE_TABS, panels, strict=True))
        self._show_side(SIDE_TABS[0], log=False)

    def _bind_shortcuts(self) -> None:
        root = self.app.root
        bindings = {
            "<Control-o>": self.browse,
            "<Control-w>": self.close_current_tab,
            "<Control-Tab>": lambda: self.cycle_tab(1),
            "<Control-Shift-Tab>": lambda: self.cycle_tab(-1),
            "<F11>": self.toggle_fullscreen,
            "<Control-F>": self.toggle_window_mode,
            "<Control-e>": self.toggle_edit_mode,
            "<Control-s>": self.save_as,
            "<Control-S>": self.save_as,
            "<Control-z>": self.undo,
            "<Control-y>": self.redo,
            "<Control-Z>": self.redo,
            "<Control-r>": lambda: self.rotate_pages(90),
            "<Control-R>": lambda: self.rotate_pages(-90),
            "<Delete>": self._on_delete_key,
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
        if (
            event.keysym.lower() in TEXT_FIELD_KEYS
            and focused is not None
            and focused.winfo_class() in ("Entry", "Text")
        ):
            return None  # copiar, deshacer o borrar dentro del campo, como siempre
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
        """
        Abre ``path`` en una pestana nueva (pide la contrasena si hace falta).
        Si ya esta abierto, muestra su pestana.
        """
        path = Path(path)
        existing = self._find_tab(path)
        if existing is not None:
            self.switch_to(existing)
            self.log("Documento ya abierto: se muestra su pestana", archivo=path.name, origen=source)
            return True
        if len(self.tabs) >= MAX_TABS:
            self.app.show_error(
                core.InvalidInputError(
                    f"Puede tener hasta {MAX_TABS} documentos abiertos. Cierre alguna pestana (Ctrl+W) para abrir otro."
                )
            )
            return False
        password = self._ask_password_until_valid(path)
        if password is False or password is True:
            return False
        try:
            session = DocumentSession.open(path, password)
        except core.PdfManagementError as error:
            self.app.show_error(error)
            return False
        self.tabs.append(DocumentTab(session))
        self.switch_to(len(self.tabs) - 1)
        self._recent = recent.add_recent(session.path)
        set_dropdown_values(self.recent_menu, self._recent_labels())
        self.recent_menu.set(RECENT_PLACEHOLDER)
        self._refresh_file_state()
        self.log(
            "Documento abierto: %s",
            session.name,
            origen=source,
            paginas=session.page_count,
            protegido=session.encrypted,
            firmas_digitales=session.has_signatures(),
            marcadores=len(session.table_of_contents()),
            pestanas=len(self.tabs),
        )
        return True

    def _find_tab(self, path: Path) -> int | None:
        target = path.resolve()
        for index, tab in enumerate(self.tabs):
            if target in (tab.session.path.resolve(), tab.path.resolve()):
                return index
        return None

    # * Pestanas --------------------------------------------------------------

    def switch_to(self, index: int) -> None:
        """Muestra la pestana ``index`` recordando como se estaba viendo la actual."""
        if not 0 <= index < len(self.tabs):
            return
        if index != self.active:
            self._remember_view()
            self.active = index
            self._load_tab()
            self.log_debug("Pestana: %s", self.tabs[index].path.name, posicion=index + 1, total=len(self.tabs))
        self._render_tabs()

    def cycle_tab(self, step: int) -> None:
        if len(self.tabs) > 1:
            self.switch_to((self.active + step) % len(self.tabs))

    def _close_tab_clicked(self, index: int) -> None:
        self.close_tab(index)

    def close_current_tab(self) -> None:
        if self.tab is not None:
            self.close_tab(self.active)

    def close_tab(self, index: int, confirm: bool = True) -> bool:
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
        tab.session.close()
        if was_active:
            self.active = min(index, len(self.tabs) - 1)
            self._load_tab()
        elif index < self.active:
            self.active -= 1
        self._render_tabs()
        self.log("Pestana cerrada", archivo=tab.path.name, quedan=len(self.tabs))
        return True

    def close_all_documents(self, confirm: bool = False) -> bool:
        while self.tabs:
            if not self.close_tab(len(self.tabs) - 1, confirm=confirm):
                return False
        return True

    def _remember_view(self) -> None:
        tab = self.tab
        if tab is None or not self.view.sizes:
            return
        tab.page = self.view.current_page
        tab.zoom = self.view.zoom_mode
        tab.scroll = self.view.canvas.yview()[0]
        tab.selection = sorted(self.thumbnails.selected)

    def _load_tab(self) -> None:
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

    def _render_tabs(self) -> None:
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

    def _update_tab_title(self) -> None:
        if self.tab is not None:
            self.tab_bar.update_tab(self.active, self._tab_info(self.tab))

    # * Pantalla completa -------------------------------------------------------

    @property
    def fullscreen(self) -> bool:
        return self.view_mode == FULLSCREEN

    def toggle_fullscreen(self) -> None:
        """Solo el visor en toda la pantalla (sin menu, barras, pestanas ni panel)."""
        self.set_view_mode(NORMAL if self.view_mode == FULLSCREEN else FULLSCREEN)

    def toggle_window_mode(self) -> None:
        """El visor ocupa toda la ventana (con las pestanas), sin pasar a pantalla completa."""
        self.set_view_mode(NORMAL if self.view_mode == WINDOW else WINDOW)

    def set_view_mode(self, mode: str) -> None:
        if mode == self.view_mode:
            return
        self.view_mode = mode
        reading = mode != NORMAL
        self.app.set_chrome_visible(not reading)
        if reading:
            self.file_bar.grid_remove()
            self.side.grid_remove()
        else:
            self.file_bar.grid()
            if self.side_visible:
                self.side.grid()
        if self.tabs and mode != FULLSCREEN:
            self.tab_bar.grid()
        else:
            self.tab_bar.grid_remove()
        self.app.root.attributes("-fullscreen", mode == FULLSCREEN)
        for button, name, active in (
            (self.window_button, "window_mode", mode == WINDOW),
            (self.fullscreen_button, "fullscreen", mode == FULLSCREEN),
        ):
            icon_name = f"exit_{name}" if active else name
            button.icon_key = icon_name
            button.configure(image=icon(icon_name, 16, style.TEXT))
        self.log("Modo de vista: %s", mode)

    def on_hide(self) -> None:
        self.set_view_mode(NORMAL)

    def _ask_password_until_valid(self, path: Path) -> str | bool | None:
        """
        Comprueba si ``path`` necesita contrasena y la pide hasta que sea
        correcta. Devuelve la contrasena (``None`` si no hace falta) o
        ``False`` si el usuario cancela o el archivo no se puede leer.
        """
        password, retry = None, False
        while True:
            try:
                core.open_document(path, password).close()
                return password
            except core.PasswordRequiredError as error:
                self.log("%s pide contrasena%s", path.name, " (la anterior no era correcta)" if retry else "")
                password = ask_password(self, path.name, retry=retry or isinstance(error, core.WrongPasswordError))
                retry = True
                if not password:
                    self.log("Cancelado: no se ingreso la contrasena", archivo=path.name)
                    return False
            except core.PdfManagementError as error:
                self.app.show_error(error)
                return False

    def _close_session(self) -> None:
        """Cierra la pestana activa sin preguntar."""
        if self.tab is not None:
            self.close_tab(self.active, confirm=False)

    def can_close(self) -> bool:
        """Al cerrar la aplicacion pregunta por cada pestana con cambios sin guardar."""
        for index, tab in enumerate(self.tabs):
            if tab.session.modified:
                self.switch_to(index)
                if not self._confirm_discard("cerrar la aplicacion"):
                    return False
        return True

    def on_close(self) -> None:
        self.search.set_document(None)
        self.view.set_document(None)
        for tab in self.tabs:
            tab.session.close()
        self.tabs.clear()
        self.active = -1

    # * Organizar paginas -----------------------------------------------------

    def rotate_pages(self, angle: int, pages: list[int] | None = None) -> bool:
        pages = pages or self.thumbnails.selection()
        return self._edit(lambda session: session.rotate(pages, angle), select=pages, page=self.view.current_page)

    def delete_pages(self, pages: list[int] | None = None) -> bool:
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

    def _move_dragged_pages(self, pages: list[int], target: int) -> None:
        self.move_pages(pages, target)

    def move_pages(self, pages: list[int], target: int) -> bool:
        """Mueve ``pages`` delante de la pagina que hoy esta en ``target`` (arrastre de miniaturas)."""
        moved: list[int] = []
        return self._edit(
            lambda session: moved.extend(session.move(pages, target)), select=lambda: moved, page=lambda: moved[0]
        )

    def insert_pdf(self, at: int | None = None) -> bool:
        """Pide un PDF y lo inserta despues de la seleccion (o antes de ``at``)."""
        if self.session is None:
            return False
        chosen = filedialog.askopenfilename(title="Insertar PDF", filetypes=(("Archivos PDF", "*.pdf"),))
        if not chosen:
            self.log_debug("Insertar PDF: dialogo cancelado")
            return False
        return self.insert_pdf_file(Path(chosen), at)

    def insert_pdf_file(self, source: Path, at: int | None = None) -> bool:
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

    def insert_blank(self, at: int | None = None) -> bool:
        if self.session is None:
            return False
        at = self._insert_position() if at is None else at
        return self._edit(lambda session: session.insert_blank(at), select=[at], page=at)

    def undo(self) -> None:
        self._step_history(redo=False)

    def redo(self) -> None:
        self._step_history(redo=True)

    def _step_history(self, redo: bool) -> None:
        session = self.session
        if session is None or not (session.history.can_redo if redo else session.history.can_undo):
            return
        label = session.redo() if redo else session.undo()
        page = min(self.view.current_page, session.page_count - 1)
        self._after_edit([page], page)
        verb = "Rehecho" if redo else "Deshecho"
        self.selection_label.configure(text=f"{verb}: {label}")
        self.log("%s: %s", verb, label, archivo=session.name, paginas=session.page_count)

    def _insert_position(self) -> int:
        return max(self.thumbnails.selection()) + 1

    def _edit(self, operation: Callable[[DocumentSession], object], *, select, page) -> bool:
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
        self._after_edit(selected, page() if callable(page) else page)
        label = session.history.undo_label
        self.selection_label.configure(text=f"{label}  ·  Ctrl+Z para deshacer")
        self.log("Edicion: %s", label, archivo=session.name, paginas=session.page_count)
        return True

    def _after_edit(self, select: list[int], page: int) -> None:
        """Tras cambiar la estructura: visor, miniaturas, marcadores y busqueda al dia."""
        session = self.session
        if session is None:
            return
        self.view.refresh(page=page)
        self.thumbnails.rebuild(keep_scroll=True)
        self.thumbnails.set_selection(select, anchor=select[0] if select else None)
        self.outline.set_entries(session.table_of_contents())
        self.search.invalidate()
        self.text_tool.clear(self.view)
        self.annotations.reset()
        self._refresh_file_state()

    def _confirm_signed_edit(self) -> bool:
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

    # * Guardar ---------------------------------------------------------------

    def save_as(self) -> bool:
        """Guarda una copia con el dialogo "Guardar como" (nunca sobre el original)."""
        if self.session is None:
            return False
        suggested = self.saved_path or self.default_output(self.session.path, "editado")
        chosen = filedialog.asksaveasfilename(
            title="Guardar como",
            defaultextension=".pdf",
            filetypes=(("Archivos PDF", "*.pdf"),),
            initialdir=str(suggested.parent),
            initialfile=suggested.name,
            parent=self,
        )
        if not chosen:
            self.log_debug("Guardar como: dialogo cancelado")
            return False
        return self.save_to(Path(chosen))

    def save_to(self, output: Path) -> bool:
        session = self.session
        if session is None:
            return False
        try:
            saved = session.save_as(output)
        except core.PdfManagementError as error:
            self.app.show_error(error)
            return False
        self.saved_path = saved
        self._refresh_file_state()
        self.log(
            "Documento guardado como: %s",
            saved.name,
            carpeta=saved.parent,
            paginas=session.page_count,
            protegido=bool(session.password),
        )
        self.app.notify_success("Documento guardado", saved)
        return True

    def _confirm_discard(self, action: str) -> bool:
        """Si hay cambios sin guardar pregunta: guardar como, descartar o cancelar."""
        session = self.session
        if session is None or not session.modified:
            return True
        answer = messagebox.askyesnocancel(
            "Cambios sin guardar",
            f"{session.name} tiene cambios sin guardar.\n\n"
            f"Desea guardarlos en un archivo nuevo antes de {action}?\n\n"
            "Si: Guardar como...\nNo: descartar los cambios\nCancelar: seguir editando",
            icon="warning",
            parent=self,
        )
        decision = {True: "guardar", False: "descartar", None: "cancelar"}[answer]
        self.log("Cambios sin guardar antes de %s: %s", action, decision, archivo=session.name)
        if answer is None:
            return False
        return self.save_as() if answer else True

    # * Acciones --------------------------------------------------------------

    def show_properties(self) -> None:
        if self.session is None:
            return
        self.log("Propiedades abiertas", archivo=self.session.name)
        size = self.view.sizes[self.view.current_page] if self.view.sizes else None
        DocumentPropertiesWindow(self, self.session.properties(), size)

    def _send_to(self, target: str) -> None:
        self.send_menu.set(SEND_PLACEHOLDER)
        session = self.session
        if session is None:
            return
        if session.modified:
            answer = messagebox.askyesnocancel(
                "Cambios sin guardar",
                f"Para enviar a {target} la version editada hay que guardarla primero.\n\n"
                "Si: Guardar como... y enviar la copia\nNo: enviar el ultimo archivo guardado\nCancelar: no enviar",
                parent=self,
            )
            if answer is None or (answer and not self.save_as()):
                return
        path = self.saved_path or session.path
        self.log("Documento enviado a %s", target, archivo=path.name)
        self.app.open_in(target, path)

    def open_search(self) -> None:
        """Muestra la barra de busqueda flotante (Ctrl+F)."""
        if self.session is None:
            return
        self.find_bar.show()
        self.log_debug("Busqueda abierta")

    def toggle_find(self) -> None:
        if self.find_bar.visible:
            self.close_find()
        else:
            self.open_search()

    def close_find(self) -> None:
        self.find_bar.hide()
        self.search.clear()
        self.view.canvas.focus_set()

    def _show_search_list(self) -> None:
        """Todos los resultados, con su contexto, en el panel lateral."""
        if not self.side_visible:
            self.toggle_side_panel()
        self.side_tabs.set("Buscar")
        self._show_side("Buscar")

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
        self.set_view_mode(NORMAL)  # Esc tambien sale de los modos de lectura
        self.find_bar.hide()
        self.annotations.cancel_tool()
        self.annotations.select(None)
        self.text_tool.clear(self.view)
        self.search.clear()

    def _on_delete_key(self) -> None:
        """Supr elimina la anotacion seleccionada; si no hay, las paginas seleccionadas."""
        if not self.annotations.delete_selected():
            self.delete_pages()

    def toggle_edit_mode(self) -> None:
        self.set_edit_mode(not self.edit_mode)

    def set_edit_mode(self, enabled: bool) -> None:
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

    def restore_tool(self) -> None:
        """Vuelve a la herramienta Texto (al terminar una herramienta de anotacion)."""
        self.tool_selector.set(TOOLS[0])
        self.view.set_tool(self.text_tool)

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
        if name == "Notas":
            self.annotations.on_panel_shown()
        if log:
            self.log_debug("Panel lateral: %s", name)

    def _choose_tool(self, name: str, log: bool = True) -> None:
        if self.annotations.active is not None:
            self.annotations.active = None
            self.annotations._refresh_tool_buttons()  # noqa: SLF001
        self.view.set_tool(self.text_tool if name == TOOLS[0] else self.hand_tool)
        if log:
            self.log("Herramienta: %s", name)

    # * Menu contextual -------------------------------------------------------

    def _on_view_right_click(self, event) -> None:
        hit = self.view.event_to_page(event)
        if hit is None or self.session is None:
            return
        if hit.page not in self.thumbnails.selected:
            self.thumbnails.set_selection([hit.page], anchor=hit.page)
        annotation = self.annotations.hit(hit)
        if annotation is not None:
            self.annotations.select(annotation)
        self._show_page_menu(hit.page, event, from_view=True, annotation=annotation)

    def _page_menu(self, from_view: bool = False, annotation=None) -> tk.Menu:
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

    def _show_page_menu(self, page: int, event, from_view: bool = False, annotation=None) -> None:
        if self.session is None:
            return
        menu = self._page_menu(from_view, annotation)
        self.log_debug("Menu de paginas abierto", pagina=page + 1, origen="visor" if from_view else "miniaturas")
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # * Estado --------------------------------------------------------------

    def _words_for(self, page: int) -> list[tuple]:
        return self.session.words(page) if self.session is not None else []

    def _on_selection_changed(self, words: int) -> None:
        self.selection_label.configure(text=f"{words} palabras seleccionadas · Ctrl+C para copiar" if words else "")

    def _on_pages_selected(self, pages: list[int]) -> None:
        if self.session is None:
            text = ""
        elif len(pages) > 1:
            text = f"{len(pages)} paginas seleccionadas"
        elif self.edit_mode:
            text = "Arrastre para reordenar"
        else:
            text = "Pulse Editar para organizar las paginas"
        if self.pages_hint.cget("text") != text:
            self.pages_hint.configure(text=text)

    def _history_tip(self, action: str, keys: str) -> str:
        history = self.session.history if self.session is not None else None
        label = (history.redo_label if action == "Rehacer" else history.undo_label) if history else None
        return f"{action}: {label} ({keys})" if label else f"{action} ({keys})"

    def _refresh_file_state(self) -> None:
        session = self.session
        self._update_tab_title()
        if session is None:
            self.file_label.configure(text="Ningun documento abierto")
            self.file_info.configure(text="Abra un PDF con el boton, con Ctrl+O o arrastrandolo al visor.")
        else:
            shown = self.saved_path or session.path
            details = [f"{session.page_count} paginas"]
            if shown.exists():
                details.append(format_size(shown.stat().st_size))
            if session.encrypted:
                details.append("protegido")
            if session.has_signatures():
                details.append("con firmas digitales")
            if session.modified:
                details.insert(0, "cambios sin guardar")
            name = shown.name + ("  •" if session.modified else "")
            if self.file_label.cget("text") != name:
                self.file_label.configure(text=name)
            self.file_info.configure(text="  ·  ".join(details) + f"  ·  {shown.parent}")
        state = "normal" if session is not None else "disabled"
        for widget in (self.send_menu, self.save_button):
            if widget.cget("state") != state:  # evitar redibujos innecesarios
                widget.configure(state=state)
        if self.search_button.cget("state") != state:
            self.search_button.configure(state=state)
        if self.edit_button.cget("state") != state:
            self.edit_button.configure(state=state)
        set_enabled(self.properties_button, session is not None)
        set_enabled(self.undo_button, session is not None and session.history.can_undo)
        set_enabled(self.redo_button, session is not None and session.history.can_redo)
        for button in (*self.page_buttons, *self.annotations.tool_buttons.values()):
            set_enabled(button, session is not None)
        self._on_pages_selected(sorted(self.thumbnails.selected))

    def _recent_labels(self) -> list[str]:
        labels = [entry.name for entry in self._recent]
        seen: dict[str, int] = {}
        for index, label in enumerate(labels):  # nombres repetidos: se agrega la carpeta
            if label in seen:
                labels[index] = f"{label}  ({self._recent[index].parent.name})"
            seen[label] = index
        return labels or ["(sin recientes)"]
