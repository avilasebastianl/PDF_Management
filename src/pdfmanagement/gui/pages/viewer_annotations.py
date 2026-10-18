"""
Anotaciones en el Visor: barra de herramientas, colores y grosor, seleccion,
movimiento, edicion de texto, menu contextual y panel "Notas".

Tambien las herramientas que cambian el contenido de la pagina (no son
anotaciones: quedan impresas en ella): reemplazar texto, texto fijo, imagen y
tapar (elimina de verdad lo que hay debajo).

Separado de ``viewer.py`` para que la pagina siga siendo legible: aqui solo
se traducen gestos a llamadas de ``DocumentSession`` (que registra cada
cambio en el historial) y se mantiene la vista al dia.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog
from typing import TYPE_CHECKING

import customtkinter as ctk
import pymupdf

from ... import core
from ...core.editing import AnnotationInfo, AnnotationStyle
from ...core.editing.annotations import DEFAULT_FONT_SIZE, FONT_SIZES, RECT_KINDS
from ...core.editing.content import contrast, text_style_at, visible_colors
from ...i18n import tr
from .. import style
from ..dropdown import dropdown_menu
from ..popup_menu import PopupMenu
from ..viewer.annotation_tools import DragTool, InkTool, MarkupTool, NoteTool, line_rects, tk_color
from ..viewer.element_tool import ElementTool, Selection
from ..viewer.inline_editor import InlineEditor
from ..viewer.page_view import PageHit, Tool
from ..viewer.panels import AnnotationsPanel
from ..widgets import ToolTip, icon_button, muted_label

if TYPE_CHECKING:
    from .viewer import ViewerPage

COLORS = {
    "Amarillo": (1.0, 0.85, 0.0),
    "Verde": (0.2, 0.75, 0.3),
    "Azul": (0.15, 0.45, 0.95),
    "Rojo": (0.9, 0.15, 0.15),
    "Negro": (0.1, 0.1, 0.1),
}
WIDTHS = {"Fino": 1.0, "Medio": 2.0, "Grueso": 4.0}
# Las claves de COLORS y WIDTHS son identificadores internos (en espanol, no cambian con el
# idioma: set_color("Rojo")); lo que se muestra es su nombre traducido.
COLOR_NAMES = {
    "Amarillo": tr("Amarillo"),
    "Verde": tr("Verde"),
    "Azul": tr("Azul"),
    "Rojo": tr("Rojo"),
    "Negro": tr("Negro"),
}
WIDTH_NAMES = {"Fino": tr("Fino"), "Medio": tr("Medio"), "Grueso": tr("Grueso")}
# Fondo de los cuadros de texto (clave interna -> color; None = transparente) y su nombre visible.
FILLS: dict[str, tuple[float, float, float] | None] = {
    "Sin fondo": None,
    "Blanco": (1.0, 1.0, 1.0),
    "Amarillo claro": (1.0, 0.97, 0.7),
    "Verde claro": (0.85, 0.96, 0.85),
    "Azul claro": (0.85, 0.92, 1.0),
    "Rosa claro": (1.0, 0.88, 0.9),
    "Gris claro": (0.92, 0.92, 0.92),
}
FILL_NAMES = {
    "Sin fondo": tr("Sin fondo"),
    "Blanco": tr("Blanco"),
    "Amarillo claro": tr("Amarillo claro"),
    "Verde claro": tr("Verde claro"),
    "Azul claro": tr("Azul claro"),
    "Rosa claro": tr("Rosa claro"),
    "Gris claro": tr("Gris claro"),
}
HANDLE_PX = 7  # lado de los tiradores para cambiar el tamano (pixeles)
CORNER_CURSORS = {"nw": "size_nw_se", "se": "size_nw_se", "ne": "size_ne_sw", "sw": "size_ne_sw"}
# (clave, icono, descripcion); None = separador
TOOLS = (
    (
        "select",
        "select",
        tr("Seleccionar: haga clic en un texto, una imagen o una anotación (doble clic edita, Supr elimina)"),
    ),
    None,
    ("highlight", "highlight", tr("Resaltar texto: arrastre sobre el texto")),
    ("underline", "underline", tr("Subrayar texto")),
    ("strikeout", "strikeout", tr("Tachar texto")),
    None,
    ("note", "note", tr("Nota: haga clic donde va")),
    ("free_text", "free_text", tr("Texto: arrastre para dibujar el cuadro (o haga clic)")),
    None,
    ("rect", "rectangle", tr("Rectángulo")),
    ("ellipse", "ellipse", tr("Elipse")),
    ("line", "line", tr("Línea")),
    ("arrow", "arrow", tr("Flecha")),
    ("ink", "ink", tr("Dibujo a mano alzada")),
    None,
    ("replace_text", "replace_text", tr("Reemplazar texto: seleccione el texto que quiere cambiar")),
    ("fixed_text", "fixed_text", tr("Texto fijo: haga clic donde va (queda escrito en la página)")),
    ("image", "image", tr("Imagen: arrastre el área donde irá (o haga clic)")),
    ("redact", "redact", tr("Tapar: arrastre sobre lo que quiere borrar (se cubre con el color del fondo)")),
)
MARKUP = ("highlight", "underline", "strikeout")
CONTENT_TOOLS = ("replace_text", "fixed_text", "image", "redact")
DEFAULT_TEXT_BOX = (220, 44)  # cuadro de texto cuando solo se hace clic
DEFAULT_IMAGE_BOX = (200, 150)  # area de la imagen cuando solo se hace clic
NOTE_BOX = (220, 40)  # campo para escribir una nota nueva
NOTE_BACKGROUND = "#FFF6BF"  # el campo de una nota se ve como un papel adhesivo
IMAGE_PATTERNS = "*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff"
HIT_TOLERANCE = 3  # puntos alrededor de la anotacion que tambien cuentan como clic


class ViewerAnnotations:
    """Une la barra de anotacion, las herramientas y el panel con la sesion abierta."""

    def __init__(self, page: ViewerPage, bar_parent, panel_parent) -> None:
        self.page = page
        self.view = page.view
        self.color = COLORS["Amarillo"]
        self.width = WIDTHS["Medio"]
        self.font_size: float = DEFAULT_FONT_SIZE
        self.fill: tuple[float, float, float] | None = None  # fondo de los cuadros de texto nuevos
        self._resize: tuple[AnnotationInfo, str, pymupdf.Rect] | None = None  # (anotacion, esquina, rect nuevo)
        self.active: str | None = None
        self.selected: AnnotationInfo | None = None
        self._cache: dict[int, list[AnnotationInfo]] = {}
        self._panel_dirty = True
        self.bar = self._build_bar(bar_parent)
        self.panel = AnnotationsPanel(
            panel_parent, on_select=self._select_from_panel, on_edit=self.edit_text, on_delete=self._delete_from_panel
        )
        self.view.add_overlay_painter(self._paint_selection)
        self.editor: InlineEditor | None = None  # campo de texto abierto sobre la pagina
        self.element: Selection | None = None  # linea de texto o imagen elegida con Seleccionar
        self.view.on_layout_changed(self._place_editor)

    # * Construccion ----------------------------------------------------------

    def _build_bar(self, parent) -> ctk.CTkFrame:
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        # Dos grupos: herramientas y estilo. Con poco ancho el estilo baja a otra fila (fit_width).
        tools = self.tools_row = ctk.CTkFrame(bar, fg_color="transparent")
        tools.grid(row=0, column=0, sticky="w")
        styles = self.style_row = ctk.CTkFrame(bar, fg_color="transparent")
        styles.grid(row=0, column=1, sticky="w", padx=(12, 0))
        self._wrapped = False
        self.tool_buttons: dict[str, ctk.CTkButton] = {}
        for entry in TOOLS:
            if entry is None:
                ctk.CTkFrame(tools, width=1, height=22, fg_color=style.CARD_BORDER).pack(side="left", padx=6)
                continue
            key, icon_name, tip = entry
            button = icon_button(tools, icon_name, lambda k=key: self.select_tool(k), tip)
            button.pack(side="left", padx=(0, 1))
            self.tool_buttons[key] = button
        bar = styles  # lo que sigue va en el grupo de estilo
        self.swatches: dict[str, ctk.CTkButton] = {}
        for name, rgb in COLORS.items():
            swatch = ctk.CTkButton(
                bar,
                text="",
                width=20,
                height=20,
                corner_radius=10,
                fg_color=tk_color(rgb),
                hover_color=tk_color(rgb),
                border_width=0,
                command=lambda n=name: self.set_color(n),
            )
            swatch.pack(side="left", padx=2)
            ToolTip(
                swatch,
                tr("Color {color} (también cambia la anotación seleccionada)", color=COLOR_NAMES[name].lower()),
            )
            self.swatches[name] = swatch
        self.width_selector = ctk.CTkSegmentedButton(
            bar, values=[WIDTH_NAMES[key] for key in WIDTHS], command=self._set_width, font=style.fonts().small
        )
        self.width_selector.set(WIDTH_NAMES["Medio"])
        self.width_selector.pack(side="left", padx=(10, 0))
        for value, button in self.width_selector._buttons_dict.items():  # noqa: SLF001 (no admite bind)
            ToolTip(button, tr("Grosor {grosor} para formas, líneas y dibujos", grosor=value.lower()))
        muted_label(bar, tr("Letra")).pack(side="left", padx=(12, 4))
        self.size_menu = dropdown_menu(
            bar, [str(size) for size in FONT_SIZES], self._set_font_size, width=64, height=28
        )
        self.size_menu.set(str(DEFAULT_FONT_SIZE))
        self.size_menu.pack(side="left")
        ToolTip(self.size_menu, tr("Tamaño de letra del texto nuevo o del cuadro de texto seleccionado"))
        muted_label(bar, tr("Fondo")).pack(side="left", padx=(12, 4))
        self.fill_button = ctk.CTkButton(
            bar,
            text="",
            width=28,
            height=24,
            corner_radius=6,
            border_width=1,
            border_color=style.CARD_BORDER,
            command=self._show_fill_menu,
        )
        self.fill_button.pack(side="left")
        ToolTip(self.fill_button, tr("Color de fondo del texto nuevo o del cuadro de texto seleccionado"))
        self._refresh_fill_button()
        self._refresh_swatches()
        return tools.master

    def fit_width(self, width: int) -> None:
        """Pone el grupo de estilo debajo de las herramientas si no caben en ``width`` pixeles."""
        wrap = self.tools_row.winfo_reqwidth() + self.style_row.winfo_reqwidth() + 12 > width
        if wrap == self._wrapped:
            return
        self._wrapped = wrap
        if wrap:
            self.style_row.grid(row=1, column=0, sticky="w", padx=0, pady=(4, 0))
        else:
            self.style_row.grid(row=0, column=1, sticky="w", padx=(12, 0), pady=0)

    # * Herramientas ----------------------------------------------------------

    def select_tool(self, key: str) -> None:
        """Activa una herramienta (o la desactiva si ya estaba activa)."""
        page = self.page
        if page.session is None:
            return
        self.close_editor()
        if not page.edit_mode:
            page.set_edit_mode(True)
        if key == self.active:
            self.cancel_tool()
            return
        if key in (*MARKUP, "replace_text") and page.text_tool.selected_words():
            # Ya hay texto seleccionado: se aplica enseguida, sin cambiar de herramienta.
            lines = line_rects(page.text_tool.selected_words())
            text = page.text_tool.selected_text()
            page.text_tool.clear(self.view)
            if key == "replace_text":
                self._replace_text(lines, text)
            else:
                self._markup(key, lines)
            return
        tools = {
            "select": lambda: ElementTool(
                elements_for=lambda index: page.session.elements(index) if page.session is not None else [],
                hit_annotation=self.hit,
                on_select=self._select_element,
                on_move=self.move,
                on_edit=self._edit_element,
                resizer=self,
            ),
            "note": lambda: NoteTool(self._note_done),
            "fixed_text": lambda: NoteTool(self._fixed_text_done),
            "ink": lambda: InkTool(self._ink_done, lambda: self.color, lambda: self.width),
        }
        tool: Tool
        if key in MARKUP:
            tool = MarkupTool(key, page._words_for, self._markup)  # noqa: SLF001
        elif key == "replace_text":
            tool = MarkupTool(key, page._words_for, self._replace_selected)  # noqa: SLF001
        elif key in tools:
            tool = tools[key]()
        else:
            tool = DragTool(key, self._drag_done, lambda: self.color, lambda: self.width)
        self.select(None)
        self.active = key
        self.view.set_tool(tool)
        self._refresh_tool_buttons()
        hint = next(tip for entry in TOOLS if entry and entry[0] == key for tip in [entry[2]])
        page.selection_label.configure(text=f"{hint}  ·  " + tr("Esc para terminar"))
        page.log("Herramienta de anotacion: %s", key)

    def cancel_tool(self) -> None:
        """Vuelve a la herramienta Texto."""
        self._clear_element()
        if self.active is None:
            return
        self.active = None
        self._refresh_tool_buttons()
        self.page.restore_tool()
        self.page.selection_label.configure(text="")

    def _refresh_tool_buttons(self) -> None:
        accent = style.accent_color()
        for key, button in self.tool_buttons.items():
            active = key == self.active
            wanted = accent if active else "transparent"
            if button.cget("fg_color") != wanted:
                button.configure(fg_color=wanted, hover_color=style.accent_hover_color() if active else style.HOVER)

    def set_color(self, name: str) -> None:
        self.color = COLORS[name]
        self._refresh_swatches()
        if self.selected is not None:
            info = self.selected
            self._run(
                lambda session: session.set_annotation_color(info.page, info.xref, self.color),
                info.page,
                select=info.xref,
            )

    def _set_font_size(self, value: str) -> None:
        self.font_size = float(value)
        info = self.selected
        if info is not None and info.kind == "FreeText" and info.font_size != self.font_size:
            self._run(
                lambda session: session.set_annotation_font_size(info.page, info.xref, self.font_size),
                info.page,
                select=info.xref,
            )

    # * Fondo de los cuadros de texto ------------------------------------------

    def _show_fill_menu(self) -> None:
        menu = PopupMenu(self.fill_button)
        for key, color in FILLS.items():
            menu.add_checkbutton(
                label=FILL_NAMES[key],
                variable=tk.BooleanVar(value=color == self.fill),
                command=lambda k=key: self.set_fill(k),  # type: ignore[misc]
            )
        button = self.fill_button
        menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height() + 4)

    def set_fill(self, key: str) -> None:
        """``key``: clave de ``FILLS``. Cambia el fondo del texto nuevo y el del cuadro seleccionado."""
        self.fill = FILLS[key]
        self._refresh_fill_button()
        info = self.selected
        if info is not None and info.kind == "FreeText" and info.fill != self.fill:
            fill = self.fill
            self._run(
                lambda session: session.set_annotation_fill(info.page, info.xref, fill), info.page, select=info.xref
            )

    def _refresh_fill_button(self) -> None:
        if self.fill is None:
            self.fill_button.configure(
                fg_color="transparent", hover_color=style.HOVER, text="∅", text_color=style.TEXT_MUTED
            )
        else:
            color = tk_color(self.fill)
            self.fill_button.configure(fg_color=color, hover_color=color, text="")

    # * Cambiar el tamano arrastrando una esquina ------------------------------------

    def _resizable(self) -> AnnotationInfo | None:
        info = self.selected
        return info if info is not None and info.kind in RECT_KINDS else None

    def handle_at(self, hit: PageHit | None) -> str | None:
        """Esquina de la anotacion seleccionada bajo el punto (``"nw"``, ``"ne"``, ``"sw"``, ``"se"``)."""
        info = self._resizable()
        if info is None or hit is None or hit.page != info.page:
            return None
        tolerance = (HANDLE_PX + 3) / self.view.scale
        corners = {
            "nw": (info.rect.x0, info.rect.y0),
            "ne": (info.rect.x1, info.rect.y0),
            "sw": (info.rect.x0, info.rect.y1),
            "se": (info.rect.x1, info.rect.y1),
        }
        for name, (x, y) in corners.items():
            if abs(hit.x - x) <= tolerance and abs(hit.y - y) <= tolerance:
                return name
        return None

    def cursor_at(self, hit: PageHit | None) -> str | None:
        corner = self.handle_at(hit)
        return CORNER_CURSORS[corner] if corner else None

    def begin_resize(self, hit: PageHit | None) -> bool:
        corner = self.handle_at(hit)
        info = self._resizable()
        if corner is None or info is None:
            return False
        self._resize = (info, corner, pymupdf.Rect(info.rect))
        return True

    def resize_drag(self, hit: PageHit | None) -> None:
        if self._resize is None or hit is None:
            return
        info, corner, _rect = self._resize
        if hit.page != info.page:
            return
        rect = pymupdf.Rect(info.rect)
        if "w" in corner:
            rect.x0 = hit.x
        else:
            rect.x1 = hit.x
        if "n" in corner:
            rect.y0 = hit.y
        else:
            rect.y1 = hit.y
        self._resize = (info, corner, rect.normalize())
        self.view.redraw_overlays()

    def end_resize(self) -> None:
        if self._resize is None:
            return
        info, _corner, rect = self._resize
        self._resize = None
        self.view.redraw_overlays()
        if abs(rect.width - info.rect.width) < 1 and abs(rect.height - info.rect.height) < 1:
            return
        self._run(lambda session: session.resize_annotation(info.page, info.xref, rect), info.page, select=info.xref)

    def _set_width(self, name: str) -> None:
        """``name``: el grosor tal como se muestra (o su clave interna, p. ej. "Grueso")."""
        key = next((key for key, shown in WIDTH_NAMES.items() if shown == name), name)
        self.width = WIDTHS[key]
        self.page.log_debug("Grosor de anotacion: %s", key)

    def _refresh_swatches(self) -> None:
        for name, swatch in self.swatches.items():
            chosen = COLORS[name] == self.color
            swatch.configure(border_width=2 if chosen else 0, border_color=style.TEXT)

    def style(self) -> AnnotationStyle:
        return AnnotationStyle(color=self.color, width=self.width)

    # * Crear -----------------------------------------------------------------

    def _markup(self, kind: str, lines: dict[int, list[pymupdf.Rect]]) -> None:
        for page_index, rects in lines.items():
            self._run(lambda session, p=page_index, r=rects: session.add_markup(p, kind, r, self.style()), page_index)

    def _note_done(self, page_index: int, point: tuple[float, float]) -> None:
        rect = pymupdf.Rect(point[0] + 24, point[1], point[0] + 24 + NOTE_BOX[0], point[1] + NOTE_BOX[1])

        def add(text: str) -> None:
            self._run(lambda session: session.add_note(page_index, point, text, self.style()), page_index)

        self.open_editor(page_index, rect, add, fontsize=11, background=NOTE_BACKGROUND, what="nota")

    # * Escribir sobre la pagina -------------------------------------------------

    def open_editor(
        self,
        page_index: int,
        rect: pymupdf.Rect,
        on_commit,
        *,
        initial: str = "",
        fontsize: float = DEFAULT_FONT_SIZE,
        color: tuple[float, float, float] = (0.0, 0.0, 0.0),
        background: str = "#FFFFFF",
        what: str = "texto",
    ) -> InlineEditor:
        """Campo de texto sobre la pagina, en lugar de un cuadro de dialogo."""
        self.close_editor()
        self.view.reveal(page_index, rect)

        def cancelled() -> None:
            self.page.log_debug("Escritura cancelada: %s", what)

        self.editor = InlineEditor(
            self.view,
            page_index,
            rect,
            on_commit=on_commit,
            on_cancel=cancelled,
            initial=initial,
            fontsize=fontsize,
            color=tk_color(color),
            background=background,
        )
        self.page.log_debug("Escribiendo sobre la pagina: %s", what, pagina=page_index + 1)
        return self.editor

    def close_editor(self) -> None:
        """Aplica el campo abierto, si lo hay (p. ej. al elegir otra herramienta)."""
        editor, self.editor = self.editor, None
        if editor is not None and not editor.done:
            editor.commit()

    def _place_editor(self) -> None:
        if self.editor is not None and not self.editor.done:
            self.editor.place()

    def _ink_done(self, page_index: int, points: list[tuple[float, float]]) -> None:
        self._run(lambda session: session.add_ink(page_index, [points], self.style()), page_index)

    # * Contenido de la pagina -------------------------------------------------

    def _replace_selected(self, _kind: str, lines: dict[int, list[pymupdf.Rect]]) -> None:
        """Fin del arrastre con la herramienta Reemplazar: el texto bajo la seleccion."""
        page_index = min(lines)
        words = self.page._words_for(page_index)  # noqa: SLF001
        rects = lines[page_index]
        text = " ".join(word[4] for word in words if any(pymupdf.Rect(word[:4]).intersects(r) for r in rects))
        self._replace_text(lines, text)

    def _replace_text(self, lines: dict[int, list[pymupdf.Rect]], current: str) -> None:
        """Pide el texto nuevo y lo escribe en lugar del seleccionado (de una pagina)."""
        page_index = min(lines)
        if len(lines) > 1:
            self.page.selection_label.configure(
                text=tr("Se reemplaza solo el texto de la primera página seleccionada.")
            )
        rects = lines[page_index]
        session = self.page.session
        if session is None:
            return
        area = pymupdf.Rect(rects[0])
        for rect in rects[1:]:
            area |= rect
        # El campo se ve como el texto original: mismo tamano, color y fondo de la pagina.
        page = session.document[page_index]
        style = text_style_at(page, rects[0])
        background, ink = visible_colors(page, rects[0])
        text_color = ink or style.color
        if contrast(text_color, background) < 3:  # que el campo siempre se lea
            text_color, background = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)

        def replace(new_text: str) -> None:
            self._run(lambda session: session.replace_text(page_index, rects, new_text), page_index)

        self.open_editor(
            page_index,
            area,
            replace,
            initial=current,
            fontsize=style.fontsize,
            color=text_color,
            background=tk_color(background),
            what="reemplazo de texto",
        )

    def _fixed_text_done(self, page_index: int, point: tuple[float, float]) -> None:
        # El amarillo (color por defecto, pensado para resaltar) no se lee sobre blanco.
        color = COLORS["Negro"] if self.color == COLORS["Amarillo"] else self.color
        size = self.font_size
        rect = pymupdf.Rect(point[0], point[1], point[0] + DEFAULT_TEXT_BOX[0], point[1] + size * 1.3)

        def add(text: str) -> None:
            self._run(lambda session: session.add_fixed_text(page_index, point, text, size, color), page_index)

        self.open_editor(page_index, rect, add, fontsize=size, color=color, what="texto fijo")

    def _image_done(self, page_index: int, rect: pymupdf.Rect) -> None:
        if rect.width < 10 or rect.height < 10:
            bounds = self.view.page_rect(page_index)
            x0 = max(min(rect.x0, bounds.width - DEFAULT_IMAGE_BOX[0] - 4), 0)
            y0 = max(min(rect.y0, bounds.height - DEFAULT_IMAGE_BOX[1] - 4), 0)
            rect = pymupdf.Rect(x0, y0, x0 + DEFAULT_IMAGE_BOX[0], y0 + DEFAULT_IMAGE_BOX[1])
        image = filedialog.askopenfilename(
            parent=self.page, title=tr("Elegir imagen"), filetypes=[(tr("Imagen"), IMAGE_PATTERNS)]
        )
        if not image:
            self.page.log_debug("Imagen cancelada")
            return
        self._run(lambda session: session.add_image(page_index, rect, image), page_index)

    def _drag_done(self, kind: str, page_index: int, start, end) -> None:
        rect = pymupdf.Rect(start, end).normalize()
        if kind == "image":
            self._image_done(page_index, rect)
            return
        if kind == "redact":
            if rect.width < 4 or rect.height < 4:
                self.page.selection_label.configure(text=tr("Arrastre sobre lo que quiere tapar  ·  Esc para terminar"))
                return
            self._run(lambda session: session.redact(page_index, rect), page_index)
            return
        if kind == "free_text":
            if rect.width < 10 or rect.height < 10:  # clic: cuadro de tamano estandar dentro de la pagina
                bounds = self.view.page_rect(page_index)
                x0 = min(start[0], bounds.width - DEFAULT_TEXT_BOX[0] - 4)
                y0 = min(start[1], bounds.height - DEFAULT_TEXT_BOX[1] - 4)
                rect = pymupdf.Rect(x0, y0, x0 + DEFAULT_TEXT_BOX[0], y0 + DEFAULT_TEXT_BOX[1])
            style_now, size, fill = self.style(), self.font_size, self.fill

            def add(text: str) -> None:
                self._run(
                    lambda session: session.add_free_text(page_index, rect, text, style_now, size, fill), page_index
                )

            self.open_editor(
                page_index,
                rect,
                add,
                fontsize=size,
                color=style_now.color,
                background=tk_color(fill) if fill else "#FFFFFF",
                what="cuadro de texto",
            )
            return
        if kind in ("line", "arrow"):
            if abs(end[0] - start[0]) + abs(end[1] - start[1]) < 4:
                self.page.selection_label.configure(text=tr("Arrastre para dibujar la línea  ·  Esc para terminar"))
                return
            self._run(
                lambda session: session.add_line(page_index, start, end, self.style(), arrow=kind == "arrow"),
                page_index,
            )
            return
        if rect.width < 4 or rect.height < 4:
            self.page.selection_label.configure(text=tr("Arrastre para dibujar la forma  ·  Esc para terminar"))
            return
        shape = "rect" if kind == "rect" else "ellipse"
        self._run(lambda session: session.add_shape(page_index, shape, rect, self.style()), page_index)

    # * Seleccion y edicion ---------------------------------------------------

    def annotations_on(self, page_index: int) -> list[AnnotationInfo]:
        if page_index not in self._cache and self.page.session is not None:
            self._cache[page_index] = self.page.session.annotations(page_index)
        return self._cache.get(page_index, [])

    def hit(self, hit: PageHit) -> AnnotationInfo | None:
        """Anotacion bajo el punto; si hay varias, la mas pequena (la que esta encima)."""
        candidates = [
            info
            for info in self.annotations_on(hit.page)
            if (info.rect + (-HIT_TOLERANCE, -HIT_TOLERANCE, HIT_TOLERANCE, HIT_TOLERANCE)).contains(
                pymupdf.Point(hit.x, hit.y)
            )
        ]
        return min(candidates, key=lambda info: info.rect.width * info.rect.height, default=None)

    def select(self, info: AnnotationInfo | None) -> None:
        if info == self.selected:
            return
        self.selected = info
        self.view.redraw_overlays()
        self.panel.show_selected(info)
        if info is not None:
            actions = [tr("Supr para eliminar")]
            if info.movable:
                actions.insert(0, tr("arrastre para mover"))
            if info.has_text:
                actions.insert(0, tr("doble clic para editar"))
            if info.kind in RECT_KINDS:
                actions.insert(0, tr("esquinas para cambiar el tamaño"))
            if info.font_size:
                actions.insert(0, tr("tamaño en Letra"))
                self.font_size = info.font_size
                self.size_menu.set(f"{info.font_size:g}")
            if info.kind == "FreeText":
                self.fill = info.fill
                self._refresh_fill_button()
            selected = tr("Anotación seleccionada: {anotacion}", anotacion=info.label)
            self.page.selection_label.configure(text="  ·  ".join([selected, *actions]))
            self.page.log_debug("Anotacion seleccionada: %s", info.label, pagina=info.page + 1)

    def move(self, info: AnnotationInfo, dx: float, dy: float) -> None:
        result: list[int] = []
        self._run(
            lambda session: result.append(session.move_annotation(info.page, info.xref, dx, dy)),
            info.page,
            select=lambda: result[0] if result else None,
        )

    def edit_text(self, info: AnnotationInfo | None = None) -> None:
        info = info or self.selected
        if info is None or not info.has_text:
            return

        def save(text: str) -> None:
            self._run(
                lambda session: session.set_annotation_text(info.page, info.xref, text), info.page, select=info.xref
            )

        if info.kind == "FreeText":
            background = tk_color(info.fill) if info.fill else "#FFFFFF"
            rect, size = info.rect, info.font_size or DEFAULT_FONT_SIZE
        else:  # nota: el campo aparece junto al icono
            rect = pymupdf.Rect(
                info.rect.x1 + 6, info.rect.y0, info.rect.x1 + 6 + NOTE_BOX[0], info.rect.y0 + NOTE_BOX[1]
            )
            size, background = 11, NOTE_BACKGROUND
        self.open_editor(
            info.page,
            rect,
            save,
            initial=info.content,
            fontsize=size,
            color=info.color if info.kind == "FreeText" and info.color else (0.0, 0.0, 0.0),
            background=background,
            what="editar anotacion",
        )

    # * Seleccionar elementos de la pagina --------------------------------------

    def _select_element(self, selection: Selection | None) -> None:
        if selection is not None and selection.annotation is not None:
            self._clear_element()
            self.select(selection.annotation)
            return
        self.select(None)
        self.element = selection
        self.view.redraw_overlays()
        if selection is None or selection.element is None:
            hint = ""
        elif selection.element.kind == "text":
            hint = tr("Línea de texto seleccionada  ·  Doble clic: editar  ·  Supr: eliminar")
        else:
            hint = tr("Imagen seleccionada  ·  Supr: eliminar")
        self.page.selection_label.configure(text=hint)

    def _clear_element(self) -> None:
        if self.element is not None:
            self.element = None
            self.view.redraw_overlays()

    def _edit_element(self, selection: Selection) -> None:
        if selection.annotation is not None:
            if selection.annotation.has_text:
                self.edit_text(selection.annotation)
            return
        element = selection.element
        if element is not None and element.kind == "text":
            self._replace_text({selection.page: [element.rect]}, element.text)

    def delete_element(self) -> bool:
        """Supr con una linea de texto o una imagen seleccionada: la elimina."""
        selection, self.element = self.element, None
        if selection is None or selection.element is None:
            return False
        element, index = selection.element, selection.page
        if element.kind == "text":
            rect = element.rect + (-1, -1, 1, 1)
            return self._run(lambda session: session.erase_text(index, rect), index)
        return self._run(lambda session: session.remove_image(index, element.rect), index)

    def delete_selected(self) -> bool:
        info = self.selected
        if info is None:
            return self.delete_element()
        self.selected = None
        return self._run(lambda session: session.delete_annotation(info.page, info.xref), info.page)

    def _delete_from_panel(self) -> None:
        self.delete_selected()

    def _select_from_panel(self, info: AnnotationInfo) -> None:
        self.view.reveal(info.page, info.rect)
        self.selected = None
        self.select(info)

    def _paint_selection(self, view) -> None:
        element = self.element
        if element is not None and element.page in view.visible_pages():
            view.draw_rect(element.page, element.rect, pad=2, outline=style.themed(style.accent_color()), width=2)
        info = self.selected
        if info is not None and info.page in view.visible_pages():
            accent = style.themed(style.accent_color())
            resizing = self._resize is not None and self._resize[0].xref == info.xref
            rect = self._resize[2] if resizing and self._resize is not None else info.rect
            view.draw_rect(info.page, rect, pad=3, outline=accent, width=2, dash=(5, 3))
            if info.kind in RECT_KINDS:
                half = HANDLE_PX / 2
                for x, y in ((rect.x0, rect.y0), (rect.x1, rect.y0), (rect.x0, rect.y1), (rect.x1, rect.y1)):
                    cx, cy = view.page_to_canvas(info.page, x, y)
                    view.canvas.create_rectangle(
                        cx - half, cy - half, cx + half, cy + half, fill=accent, outline="white", tags="overlay"
                    )

    # * Menu contextual -------------------------------------------------------

    def add_menu_items(self, menu: PopupMenu, info: AnnotationInfo) -> None:
        if info.has_text:
            menu.add_command(
                label=tr("Editar {anotacion}...", anotacion=info.label.lower()), command=lambda: self.edit_text(info)
            )
        colors = PopupMenu(menu.master)
        for name in COLORS:
            colors.add_command(
                label=COLOR_NAMES[name],
                command=lambda n=name: self._recolor(info, n),  # type: ignore[misc]
            )
        menu.add_cascade(label=tr("Color"), menu=colors)
        menu.add_command(
            label=tr("Eliminar {anotacion}", anotacion=info.label.lower()),
            accelerator=tr("Supr"),
            command=lambda: self._delete(info),
        )
        menu.add_separator()

    def _recolor(self, info: AnnotationInfo, name: str) -> None:
        self.select(info)
        self.set_color(name)

    def _delete(self, info: AnnotationInfo) -> None:
        self.select(info)
        self.delete_selected()

    # * Aplicar cambios -------------------------------------------------------

    def _run(self, operation, page_index: int, select=None) -> bool:
        """Ejecuta un cambio de anotacion y vuelve a dibujar solo esa pagina."""
        page = self.page
        session = page.session
        if session is None or not page._confirm_signed_edit():  # noqa: SLF001
            return False
        steps = session.history.undo_depth
        try:
            operation(session)
        except core.PdfManagementError as error:
            page.app.show_error(error)
            return False
        if session.history.undo_depth == steps:
            return False
        # La pagina ya se redibujo con el aviso de cambios (content_changed); aqui solo la seleccion.
        xref = select() if callable(select) else select
        self.selected = next((info for info in self.annotations_on(page_index) if info.xref == xref), None)
        self.panel.show_selected(self.selected)
        self.view.redraw_overlays()
        label = session.history.undo_label
        page.selection_label.configure(text=f"{label}  ·  " + tr("Ctrl+Z para deshacer"))
        page.log("Anotacion: %s", label, archivo=session.name)
        return True

    def content_changed(self, pages) -> None:
        """Cambiaron las anotaciones de ``pages`` (aviso de la sesion)."""
        if self.element is not None and self.element.page in pages:
            self.element = None
        for page in pages:
            self._cache.pop(page, None)
        self.refresh_panel()

    def reset(self) -> None:
        """El documento cambio por completo (abrir, deshacer, editar paginas)."""
        if self.editor is not None and not self.editor.done:
            self.editor.cancel()  # el campo apuntaba a una pagina que pudo cambiar
        self.editor = None
        self.element = None
        self._cache.clear()
        if self.selected is not None and self.page.session is not None:
            current = (
                self.annotations_on(self.selected.page) if self.selected.page < self.page.session.page_count else []
            )
            self.selected = next((info for info in current if info.xref == self.selected.xref), None)
        else:
            self.selected = None
        self.refresh_panel()

    def refresh_panel(self) -> None:
        """Actualiza la lista solo si esta a la vista (si no, al mostrarla)."""
        if not self.panel.winfo_ismapped():
            self._panel_dirty = True
            return
        self._panel_dirty = False
        session = self.page.session
        self.panel.set_annotations(session.annotations() if session is not None else [], self.selected)

    def on_panel_shown(self) -> None:
        if self._panel_dirty:
            self._panel_dirty = False
            session = self.page.session
            self.panel.set_annotations(session.annotations() if session is not None else [], self.selected)
