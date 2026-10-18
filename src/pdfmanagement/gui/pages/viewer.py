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
terminar la herramienta de anotacion y limpiar la seleccion, Ctrl+P imprimir.

Opciones de lectura (boton "Ver", ver viewer_display.py): modo nocturno, dos
paginas, comparar con otra pestana (vista dividida) e imprimir. Panel
"Firmas": verifica las firmas digitales y permite firmar.
"""

import tkinter as tk
from collections.abc import Callable
from pathlib import Path

import customtkinter as ctk

from ... import recent
from ...i18n import tr, trn
from .. import style
from ..dropdown import dropdown_menu
from ..viewer import FIT_WIDTH, HandTool, PageView, ThumbnailStrip, ViewerToolbar
from ..viewer.annotation_tools import SelectTool
from ..viewer.compare import ComparePanel
from ..viewer.find_bar import FindBar
from ..viewer.icon_tabs import IconTabs
from ..viewer.panels import OutlinePanel, SearchPanel
from ..viewer.signatures_panel import SignaturesPanel
from ..viewer.tab_strip import TabStrip
from ..widgets import ToolTip, format_size, icon_button, muted_label, primary_button, secondary_button, set_enabled
from .base import BasePage
from .viewer_annotations import ViewerAnnotations
from .viewer_display import DisplayMixin
from .viewer_files import RECENT_PLACEHOLDER, SEND_PLACEHOLDER, SEND_TARGETS, FilesMixin
from .viewer_modes import NORMAL, WINDOW, ModesMixin
from .viewer_organize import OrganizeMixin
from .viewer_tabs import DocumentTab, TabsMixin

# Textos mostrados en los selectores (ya traducidos: el idioma se fija antes de importar
# la interfaz). El codigo los usa por posicion: SIDE_TABS[2] es "Buscar", TOOLS[0] "Texto".
SIDE_TABS = (tr("Páginas"), tr("Marcadores"), tr("Buscar"), tr("Notas"), tr("Firmas"))
PAGES_TAB, OUTLINE_TAB, SEARCH_TAB, NOTES_TAB, SIGNATURES_TAB = SIDE_TABS
SIDE_ICONS = ("pages_tab", "outline", "search", "note", "signature")
SIDE_WIDTH = 272
TOOLS = (tr("Texto"), tr("Mano"))
PLACEHOLDER = (
    tr("Abra un PDF, arrástrelo aquí o cree uno nuevo"),
    tr("Lea, busque (Ctrl+F), anote y organice las páginas. Ctrl+O abre un PDF y Ctrl+N crea uno nuevo."),
)
# Teclas que dentro de un campo de texto conservan su funcion normal.
TEXT_FIELD_KEYS = {"c", "a", "z", "y", "delete"}
TEXT_BUTTON_WIDTH = 92  # Buscar y Editar con texto; con poco ancho quedan solo con icono (30)


class ViewerPage(TabsMixin, FilesMixin, OrganizeMixin, ModesMixin, DisplayMixin, BasePage):
    name = "Visor"  # identificador de la seccion (no se traduce)
    title = tr("Visor de PDF")
    subtitle = tr("Lea, busque, anote y organice las páginas de cualquier PDF.")
    icon_name = "pdf"
    scrollable = False
    show_header = False  # el visor aprovecha todo el alto; el titulo ya lo indica el menu lateral

    # Estado compartido por los mixins (se asigna en build).
    tabs: list[DocumentTab]
    active: int
    view_mode: str
    edit_mode: bool
    compare: ComparePanel | None
    compare_tab: DocumentTab | None
    night_mode: tk.BooleanVar
    two_pages: tk.BooleanVar

    def build(self) -> None:
        self.tabs: list[DocumentTab] = []
        self.active = -1  # indice de la pestana visible (-1: ninguna)
        self.view_mode = NORMAL  # NORMAL, WINDOW (toda la ventana) o FULLSCREEN
        self._recent: list[Path] = recent.load_recent()
        self.compare = None  # vista dividida (se crea la primera vez que se compara)
        self.compare_tab = None
        self._compare_unsubscribe: Callable[[], None] | None = None
        self._verified_path: Path | None = None  # archivo cuyas firmas muestra el panel
        self._new_documents = 0  # numera los documentos nuevos de la sesion
        # Todo el espacio sobrante es para el visor (BasePage da peso a la columna 0).
        self.body.grid_columnconfigure(0, weight=0)
        self.body.grid_columnconfigure(1, weight=1)
        self.body.grid_rowconfigure(2, weight=1)
        self._build_file_bar()
        self._build_tab_bar()
        self._build_side_panel()
        self._build_viewer()
        self.apply_display_settings()
        self._bind_shortcuts()
        self._refresh_file_state()

    # * Construccion ----------------------------------------------------------

    def _build_file_bar(self) -> None:
        bar = self.file_bar = ctk.CTkFrame(self.body, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, style.GAP))
        bar.grid_columnconfigure(2, weight=1)
        start = ctk.CTkFrame(bar, fg_color="transparent")
        start.grid(row=0, column=0)
        primary_button(start, tr("Abrir"), self.browse, "folder", width=110).pack(side="left")
        self.new_button = secondary_button(start, tr("Nuevo PDF"), self.new_document, "add", width=130, height=38)
        self.new_button.pack(side="left", padx=(8, 0))
        ToolTip(self.new_button, tr("Crear un PDF en blanco o desde una plantilla (Ctrl+N)"))
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
            history, "info", self.show_properties, tr("Propiedades del documento"), size=34, state="disabled"
        )
        self.properties_button.pack(side="left", padx=(2, 0))
        self.print_button = icon_button(
            history, "print", self.print_document, tr("Imprimir (Ctrl+P)"), size=34, state="disabled"
        )
        self.print_button.pack(side="left", padx=(2, 0))
        self.save_button = secondary_button(bar, tr("Guardar como"), self.save_as, "save_as", width=140)
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
            width=SIDE_WIDTH,
        )
        self.side.grid(row=2, column=0, sticky="nsw", padx=(0, style.GAP), pady=(0, style.COMPACT_PAD))
        self.side.grid_propagate(False)
        self.side.pack_propagate(False)
        self.side_tabs = IconTabs(self.side, list(zip(SIDE_TABS, SIDE_ICONS, strict=True)), self._show_side)
        self.side_tabs.pack(fill="x", padx=8, pady=8)
        self.side_stack = ctk.CTkFrame(self.side, fg_color="transparent")
        self.side_stack.pack(fill="both", expand=True, padx=2, pady=(0, 8))
        self.side_visible = True

    def _build_pages_panel(self) -> ctk.CTkFrame:
        """Miniaturas con la barra de organizacion encima."""
        panel = ctk.CTkFrame(self.side_stack, fg_color="transparent")
        tools = self.page_tools = ctk.CTkFrame(panel, fg_color="transparent")  # visible en modo edicion
        self.page_buttons = [
            icon_button(
                tools, "rotate_left", lambda: self.rotate_pages(-90), tr("Rotar a la izquierda (Ctrl+Mayús+R)")
            ),
            icon_button(tools, "rotate_right", lambda: self.rotate_pages(90), tr("Rotar a la derecha (Ctrl+R)")),
            icon_button(tools, "delete", self.delete_pages, tr("Eliminar las páginas seleccionadas (Supr)")),
            icon_button(tools, "insert_pdf", self.insert_pdf, tr("Insertar otro PDF después de la selección")),
            icon_button(
                tools, "blank_page", self.insert_blank, tr("Insertar una página en blanco después de la selección")
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
        self.viewer_card = card

        # Visor principal y, al comparar, el segundo visor a su derecha.
        self.view_area = ctk.CTkFrame(card, fg_color="transparent", corner_radius=0)
        self.view_area.grid_columnconfigure(0, weight=1)
        self.view_area.grid_rowconfigure(0, weight=1)
        self.view = PageView(
            self.view_area, continuous=True, placeholder=PLACEHOLDER, on_empty_click=self.browse, on_drop=self._on_drop
        )
        self.view.grid(row=0, column=0, sticky="nsew")
        self.view.on_page_changed(self.sync_compare)
        # Sin documento: botones grandes en el centro del visor (abrir o crear).
        self.empty_actions = ctk.CTkFrame(self.view, fg_color=style.CANVAS_BG, corner_radius=0)
        primary_button(self.empty_actions, tr("Abrir PDF"), self.browse, "folder", width=150).pack(side="left", padx=6)
        secondary_button(
            self.empty_actions, tr("Nuevo PDF"), self.new_document, "add", width=150, height=38, fg_color=style.CARD_BG
        ).pack(side="left", padx=6)
        top = self.top_bar = ctk.CTkFrame(card, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 6))
        self._top_compact = False  # botones Buscar y Editar solo con icono (poco ancho)
        self._top_full_width = 0
        icon_button(top, "list", self.toggle_side_panel, tr("Mostrar u ocultar el panel lateral")).pack(
            side="left", padx=(0, 6)
        )
        self.toolbar = ViewerToolbar(top, self.view)
        self.toolbar.pack(side="left", fill="x", expand=True)
        self.tool_selector = ctk.CTkSegmentedButton(
            top, values=list(TOOLS), command=self._choose_tool, font=style.fonts().small
        )
        self.tool_selector.set(TOOLS[0])
        self.tool_selector.pack(side="left", padx=(10, 6))
        tips = {TOOLS[0]: tr("Seleccionar y copiar texto (Ctrl+C)"), TOOLS[1]: tr("Arrastrar para mover la página")}
        for value, button in self.tool_selector._buttons_dict.items():  # noqa: SLF001 (no admite bind)
            ToolTip(button, tips[value])
        self.search_button = secondary_button(
            top, tr("Buscar"), self.toggle_find, "search", width=TEXT_BUTTON_WIDTH, height=30
        )
        self.search_button.pack(side="left")
        ToolTip(self.search_button, tr("Buscar palabras en el documento (Ctrl+F)"))
        self.edit_button = secondary_button(
            top, tr("Editar"), self.toggle_edit_mode, "edit", width=TEXT_BUTTON_WIDTH, height=30
        )
        self.edit_button.pack(side="left", padx=(6, 0))
        ToolTip(self.edit_button, tr("Mostrar u ocultar las herramientas para anotar y organizar páginas (Ctrl+E)"))
        self.window_button = icon_button(
            top,
            "window_mode",
            self.toggle_window_mode,
            lambda: (
                tr("Volver a la vista normal (Ctrl+Mayús+F o Esc)")
                if self.view_mode == WINDOW
                else tr("Visor en toda la ventana para leer (Ctrl+Mayús+F)")
            ),
        )
        self.view_button = icon_button(
            top, "view_options", self.show_view_menu, tr("Ver: modo nocturno, dos páginas, comparar e imprimir")
        )
        self.view_button.pack(side="left", padx=(6, 0))
        self.window_button.pack(side="left", padx=(2, 0))
        self.fullscreen_button = icon_button(
            top,
            "fullscreen",
            self.toggle_fullscreen,
            lambda: tr("Salir de pantalla completa (F11 o Esc)") if self.fullscreen else tr("Pantalla completa (F11)"),
        )
        self.fullscreen_button.pack(side="left", padx=(2, 0))
        ctk.CTkFrame(card, height=1, corner_radius=0, fg_color=style.CARD_BORDER).grid(
            row=2, column=0, sticky="ew", padx=1
        )
        self.view_area.grid(row=3, column=0, sticky="nsew", padx=8, pady=8)
        card.bind("<Configure>", self.fit_bars, add="+")
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
            resizer=lambda: self.annotations,
        )
        self.hand_tool = HandTool()
        self.view.set_tool(self.text_tool)

        self.pages_panel = self._build_pages_panel()
        self.outline = OutlinePanel(self.side_stack, self.view)
        self.search = SearchPanel(self.side_stack, self.view)
        self.annotations = ViewerAnnotations(self, card, self.side_stack)
        self.signatures = SignaturesPanel(
            self.side_stack, on_verify=lambda: self.refresh_signatures(force=True), on_sign=self.sign_from_viewer
        )
        self.find_bar = FindBar(self.view, self.search, on_show_list=self._show_search_list, on_close=self.close_find)
        self.annotations.bar.grid(row=1, column=0, sticky="w", padx=12, pady=(0, 6))
        self.annotations.bar.grid_remove()  # aparece con el boton Editar
        self.edit_mode = False
        panels = (self.pages_panel, self.outline, self.search, self.annotations.panel, self.signatures)
        self._side_panels = dict(zip(SIDE_TABS, panels, strict=True))
        self._show_side(SIDE_TABS[0], log=False)

    def _bind_shortcuts(self) -> None:
        root = self.app.root
        bindings = {
            "<Control-o>": self.browse,
            "<Control-n>": self.new_document,
            "<Control-p>": self.print_document,
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

    # * Barras adaptables --------------------------------------------------------

    def fit_bars(self, _event=None) -> None:
        """
        Con poco ancho (textos largos en otro idioma, comparar documentos,
        ventana chica) Buscar y Editar quedan solo con icono y la barra de
        anotacion pasa a dos filas, en vez de cortarse por la derecha.
        """
        width = self.viewer_card.winfo_width() - 20
        if width <= 50:
            return
        if not self._top_compact:
            self._top_full_width = self.top_bar.winfo_reqwidth()
        compact = self._top_full_width > width
        if compact != self._top_compact:
            self._top_compact = compact
            button_width = 30 if compact else TEXT_BUTTON_WIDTH
            self.search_button.configure(text="" if compact else tr("Buscar"), width=button_width)
            self.edit_button.configure(text=self.edit_button_text(), width=button_width)
            self.log_debug("Barra del visor %s", "compacta" if compact else "completa", ancho=width)
        self.annotations.fit_width(width)

    def edit_button_text(self) -> str:
        if self._top_compact:
            return ""
        return tr("Listo") if self.edit_mode else tr("Editar")

    # * Acciones --------------------------------------------------------------

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
        self.side_tabs.set(SEARCH_TAB)
        self._show_side(SEARCH_TAB)

    def copy_selection(self) -> None:
        text = self.text_tool.selected_text()
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.selection_label.configure(
            text=trn(
                "Copiado al portapapeles: {count} carácter", "Copiado al portapapeles: {count} caracteres", len(text)
            )
        )
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
        if name == NOTES_TAB:
            self.annotations.on_panel_shown()
        elif name == SIGNATURES_TAB:
            self.refresh_signatures()
        if log:
            self.log_debug("Panel lateral: %s", name)

    def _choose_tool(self, name: str, log: bool = True) -> None:
        if self.annotations.active is not None:
            self.annotations.active = None
            self.annotations._refresh_tool_buttons()  # noqa: SLF001
        self.view.set_tool(self.text_tool if name == TOOLS[0] else self.hand_tool)
        if log:
            self.log("Herramienta: %s", name)

    # * Estado --------------------------------------------------------------

    def _words_for(self, page: int) -> list[tuple]:
        return self.session.words(page) if self.session is not None else []

    def _on_selection_changed(self, words: int) -> None:
        text = ""
        if words:
            text = trn(
                "{count} palabra seleccionada · Ctrl+C para copiar",
                "{count} palabras seleccionadas · Ctrl+C para copiar",
                words,
            )
        self.selection_label.configure(text=text)

    def _on_pages_selected(self, pages: list[int]) -> None:
        if self.session is None:
            text = ""
        elif len(pages) > 1:
            text = trn("{count} página seleccionada", "{count} páginas seleccionadas", len(pages))
        elif self.edit_mode:
            text = tr("Arrastre para reordenar")
        else:
            text = tr("Pulse Editar para organizar las páginas")
        if self.pages_hint.cget("text") != text:
            self.pages_hint.configure(text=text)

    def _history_tip(self, action: str, keys: str) -> str:
        """``action``: "Deshacer" o "Rehacer" (identificador; se muestra traducido)."""
        redo = action == "Rehacer"
        shown = tr("Rehacer") if redo else tr("Deshacer")
        history = self.session.history if self.session is not None else None
        label = (history.redo_label if redo else history.undo_label) if history else None
        if label:
            return tr("{accion}: {cambio} ({teclas})", accion=shown, cambio=label, teclas=keys)
        return f"{shown} ({keys})"

    def _refresh_file_state(self) -> None:
        session = self.session
        self._update_tab_title()
        if session is None:
            self.file_label.configure(text=tr("Ningún documento abierto"))
            self.file_info.configure(text=tr("Abra un PDF con el botón, con Ctrl+O o arrastrándolo al visor."))
        else:
            shown = self.saved_path or session.path
            details = [trn("{count} página", "{count} páginas", session.page_count)]
            if shown.exists():
                details.append(format_size(shown.stat().st_size))
            if session.encrypted:
                details.append(tr("protegido"))
            if session.has_signatures():
                details.append(tr("con firmas digitales"))
            if session.modified:
                details.insert(0, tr("cambios sin guardar"))
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
        if session is None:
            self.empty_actions.place(relx=0.5, rely=0.5, y=78, anchor="n")
        else:
            self.empty_actions.place_forget()
        set_enabled(self.print_button, session is not None)
        set_enabled(self.undo_button, session is not None and session.history.can_undo)
        set_enabled(self.redo_button, session is not None and session.history.can_redo)
        for button in (*self.page_buttons, *self.annotations.tool_buttons.values()):
            set_enabled(button, session is not None)
        self._on_pages_selected(sorted(self.thumbnails.selected))
