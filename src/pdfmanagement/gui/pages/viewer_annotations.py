"""
Anotaciones en el Visor: barra de herramientas, colores y grosor, seleccion,
movimiento, edicion de texto, menu contextual y panel "Notas".

Separado de ``viewer.py`` para que la pagina siga siendo legible: aqui solo
se traducen gestos a llamadas de ``DocumentSession`` (que registra cada
cambio en el historial) y se mantiene la vista al dia.
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

import customtkinter as ctk
import pymupdf

from ... import core
from ...core.editing import AnnotationInfo, AnnotationStyle
from ...core.editing.annotations import DEFAULT_FONT_SIZE, FONT_SIZES
from .. import style
from ..dialogs import ask_text
from ..dropdown import dropdown_menu
from ..viewer.annotation_tools import DragTool, InkTool, MarkupTool, NoteTool, line_rects, tk_color
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
# (clave, icono, descripcion); None = separador
TOOLS = (
    ("highlight", "highlight", "Resaltar texto: arrastre sobre el texto"),
    ("underline", "underline", "Subrayar texto"),
    ("strikeout", "strikeout", "Tachar texto"),
    None,
    ("note", "note", "Nota: haga clic donde va"),
    ("free_text", "free_text", "Texto: arrastre para dibujar el cuadro (o haga clic)"),
    None,
    ("rect", "rectangle", "Rectangulo"),
    ("ellipse", "ellipse", "Elipse"),
    ("line", "line", "Linea"),
    ("arrow", "arrow", "Flecha"),
    ("ink", "ink", "Dibujo a mano alzada"),
)
MARKUP = ("highlight", "underline", "strikeout")
DEFAULT_TEXT_BOX = (220, 44)  # cuadro de texto cuando solo se hace clic
HIT_TOLERANCE = 3  # puntos alrededor de la anotacion que tambien cuentan como clic


class ViewerAnnotations:
    """Une la barra de anotacion, las herramientas y el panel con la sesion abierta."""

    def __init__(self, page: ViewerPage, bar_parent, panel_parent) -> None:
        self.page = page
        self.view = page.view
        self.color = COLORS["Amarillo"]
        self.width = WIDTHS["Medio"]
        self.font_size: float = DEFAULT_FONT_SIZE
        self.active: str | None = None
        self.selected: AnnotationInfo | None = None
        self._cache: dict[int, list[AnnotationInfo]] = {}
        self._panel_dirty = True
        self.bar = self._build_bar(bar_parent)
        self.panel = AnnotationsPanel(
            panel_parent, on_select=self._select_from_panel, on_edit=self.edit_text, on_delete=self._delete_from_panel
        )
        self.view.add_overlay_painter(self._paint_selection)

    # * Construccion ----------------------------------------------------------

    def _build_bar(self, parent) -> ctk.CTkFrame:
        bar = ctk.CTkFrame(parent, fg_color="transparent")
        self.tool_buttons: dict[str, ctk.CTkButton] = {}
        for entry in TOOLS:
            if entry is None:
                ctk.CTkFrame(bar, width=1, height=22, fg_color=style.CARD_BORDER).pack(side="left", padx=6)
                continue
            key, icon_name, tip = entry
            button = icon_button(bar, icon_name, lambda k=key: self.select_tool(k), tip)
            button.pack(side="left", padx=(0, 1))
            self.tool_buttons[key] = button
        ctk.CTkFrame(bar, width=1, height=22, fg_color=style.CARD_BORDER).pack(side="left", padx=6)
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
            ToolTip(swatch, f"Color {name.lower()} (tambien cambia la anotacion seleccionada)")
            self.swatches[name] = swatch
        self.width_selector = ctk.CTkSegmentedButton(
            bar, values=list(WIDTHS), command=self._set_width, font=style.fonts().small
        )
        self.width_selector.set("Medio")
        self.width_selector.pack(side="left", padx=(10, 0))
        for value, button in self.width_selector._buttons_dict.items():  # noqa: SLF001 (no admite bind)
            ToolTip(button, f"Grosor {value.lower()} para formas, lineas y dibujos")
        muted_label(bar, "Letra").pack(side="left", padx=(12, 4))
        self.size_menu = dropdown_menu(
            bar, [str(size) for size in FONT_SIZES], self._set_font_size, width=64, height=28
        )
        self.size_menu.set(str(DEFAULT_FONT_SIZE))
        self.size_menu.pack(side="left")
        ToolTip(self.size_menu, "Tamano de letra del texto nuevo o del cuadro de texto seleccionado")
        self._refresh_swatches()
        return bar

    # * Herramientas ----------------------------------------------------------

    def select_tool(self, key: str) -> None:
        """Activa una herramienta (o la desactiva si ya estaba activa)."""
        page = self.page
        if page.session is None:
            return
        if not page.edit_mode:
            page.set_edit_mode(True)
        if key == self.active:
            self.cancel_tool()
            return
        if key in MARKUP and page.text_tool.selected_words():
            # Ya hay texto seleccionado: se marca enseguida, sin cambiar de herramienta.
            lines = line_rects(page.text_tool.selected_words())
            page.text_tool.clear(self.view)
            self._markup(key, lines)
            return
        tools = {
            "note": lambda: NoteTool(self._note_done),
            "ink": lambda: InkTool(self._ink_done, lambda: self.color, lambda: self.width),
        }
        tool: Tool
        if key in MARKUP:
            tool = MarkupTool(key, page._words_for, self._markup)  # noqa: SLF001
        elif key in tools:
            tool = tools[key]()
        else:
            tool = DragTool(key, self._drag_done, lambda: self.color, lambda: self.width)
        self.select(None)
        self.active = key
        self.view.set_tool(tool)
        self._refresh_tool_buttons()
        hint = next(tip for entry in TOOLS if entry and entry[0] == key for tip in [entry[2]])
        page.selection_label.configure(text=f"{hint}  ·  Esc para terminar")
        page.log("Herramienta de anotacion: %s", key)

    def cancel_tool(self) -> None:
        """Vuelve a la herramienta Texto."""
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

    def _set_width(self, name: str) -> None:
        self.width = WIDTHS[name]
        self.page.log_debug("Grosor de anotacion: %s", name)

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
        text = ask_text(self.page, "Nueva nota", "Escriba el comentario de la nota:")
        if text is None:
            self.page.log_debug("Nota cancelada")
            return
        self._run(lambda session: session.add_note(page_index, point, text, self.style()), page_index)

    def _ink_done(self, page_index: int, points: list[tuple[float, float]]) -> None:
        self._run(lambda session: session.add_ink(page_index, [points], self.style()), page_index)

    def _drag_done(self, kind: str, page_index: int, start, end) -> None:
        rect = pymupdf.Rect(start, end).normalize()
        if kind == "free_text":
            if rect.width < 10 or rect.height < 10:  # clic: cuadro de tamano estandar dentro de la pagina
                bounds = self.view.page_rect(page_index)
                x0 = min(start[0], bounds.width - DEFAULT_TEXT_BOX[0] - 4)
                y0 = min(start[1], bounds.height - DEFAULT_TEXT_BOX[1] - 4)
                rect = pymupdf.Rect(x0, y0, x0 + DEFAULT_TEXT_BOX[0], y0 + DEFAULT_TEXT_BOX[1])
            text = ask_text(self.page, "Texto sobre la pagina", "Escriba el texto que aparecera en la pagina:")
            if text is None:
                self.page.log_debug("Texto cancelado")
                return
            self._run(
                lambda session: session.add_free_text(page_index, rect, text, self.style(), self.font_size), page_index
            )
            return
        if kind in ("line", "arrow"):
            if abs(end[0] - start[0]) + abs(end[1] - start[1]) < 4:
                self.page.selection_label.configure(text="Arrastre para dibujar la linea  ·  Esc para terminar")
                return
            self._run(
                lambda session: session.add_line(page_index, start, end, self.style(), arrow=kind == "arrow"),
                page_index,
            )
            return
        if rect.width < 4 or rect.height < 4:
            self.page.selection_label.configure(text="Arrastre para dibujar la forma  ·  Esc para terminar")
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
            actions = ["Supr para eliminar"]
            if info.movable:
                actions.insert(0, "arrastre para mover")
            if info.has_text:
                actions.insert(0, "doble clic para editar")
            if info.font_size:
                actions.insert(0, "tamano en Letra")
                self.font_size = info.font_size
                self.size_menu.set(f"{info.font_size:g}")
            self.page.selection_label.configure(text=f"{info.label} seleccionada  ·  " + "  ·  ".join(actions))
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
        text = ask_text(self.page, f"Editar {info.label.lower()}", "Texto de la anotacion:", initial=info.content)
        if text is None or text == info.content:
            return
        self._run(lambda session: session.set_annotation_text(info.page, info.xref, text), info.page, select=info.xref)

    def delete_selected(self) -> bool:
        info = self.selected
        if info is None:
            return False
        self.selected = None
        return self._run(lambda session: session.delete_annotation(info.page, info.xref), info.page)

    def _delete_from_panel(self) -> None:
        self.delete_selected()

    def _select_from_panel(self, info: AnnotationInfo) -> None:
        self.view.reveal(info.page, info.rect)
        self.selected = None
        self.select(info)

    def _paint_selection(self, view) -> None:
        info = self.selected
        if info is not None and info.page in view.visible_pages():
            view.draw_rect(
                info.page,
                info.rect,
                pad=3,
                outline=style.themed(style.accent_color()),
                width=2,
                dash=(5, 3),
            )

    # * Menu contextual -------------------------------------------------------

    def add_menu_items(self, menu: tk.Menu, info: AnnotationInfo) -> None:
        if info.has_text:
            menu.add_command(label=f"Editar texto de la {info.label.lower()}...", command=lambda: self.edit_text(info))
        colors = tk.Menu(menu, tearoff=0)
        for name in COLORS:
            colors.add_command(label=name, command=lambda n=name: self._recolor(info, n))  # type: ignore[misc]
        menu.add_cascade(label="Color", menu=colors)
        menu.add_command(
            label=f"Eliminar {info.label.lower()}",
            accelerator="Supr",
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
        self._cache.pop(page_index, None)
        xref = select() if callable(select) else select
        self.selected = next((info for info in self.annotations_on(page_index) if info.xref == xref), None)
        self.view.refresh({page_index})
        page.thumbnails.refresh_pages([page_index])
        self.refresh_panel()
        page._refresh_file_state()  # noqa: SLF001
        label = session.history.undo_label
        page.selection_label.configure(text=f"{label}  ·  Ctrl+Z para deshacer")
        page.log("Anotacion: %s", label, archivo=session.name)
        return True

    def reset(self) -> None:
        """El documento cambio por completo (abrir, deshacer, editar paginas)."""
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
