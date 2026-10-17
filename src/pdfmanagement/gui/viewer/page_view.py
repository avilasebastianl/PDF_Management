"""
Visor de paginas reutilizable (seccion Visor, Firmar y futuras herramientas).

- Modo continuo (todas las paginas en columna) o de pagina unica.
- Desplazamiento virtualizado: solo se dibujan las paginas visibles (y una de
  margen); las lejanas liberan su imagen. Abrir un PDF de cientos de paginas
  cuesta lo mismo que abrir uno de una.
- Zoom: ajustar a ancho, ajustar a pagina o porcentaje; con Ctrl + rueda el
  punto bajo el cursor queda fijo.
- Capas sobre las paginas: resaltado de busqueda, seleccion y la herramienta
  activa (``Tool``), que reciben coordenadas en puntos de la pagina.

Coordenadas: el lienzo usa pixeles; las paginas, puntos PDF (72 pt = 1 pulgada)
sobre la pagina tal como se ve (con su rotacion). ``scale`` = pixeles por punto.
"""

from __future__ import annotations

import bisect
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass

import customtkinter as ctk
import pymupdf
from PIL import ImageTk

from .. import style
from ..events import debug_event
from ..icons import GLYPHS, render_glyph
from ..widgets import enable_file_drop, hide, show
from .render import RenderScheduler, scale_key

MARGIN = 24
GAP = 16
BASE_SCALE = 96 / 72                 # 100 % = tamano real en una pantalla de 96 ppp
ZOOM_STEPS = (25, 33, 50, 67, 75, 90, 100, 110, 125, 150, 175, 200, 250, 300, 400, 500)
FIT_WIDTH = "fit_width"
FIT_PAGE = "fit_page"
KEEP_RENDERED = 3                    # paginas dibujadas que se conservan fuera de la vista
TILE_PX = 1024                       # lado de cada mosaico con zoom alto
TILE_THRESHOLD_PX = 2_500_000        # paginas mas grandes que esto se dibujan por mosaicos
RESIZE_DEBOUNCE_MS = 120
HIGHLIGHT = ("#F9D648", "#F9D648")
HIGHLIGHT_CURRENT = ("#F28C28", "#FFA94D")
SELECTION = ("#3B82F6", "#60A5FA")


@dataclass(frozen=True)
class PageHit:
    """Punto del lienzo traducido a una pagina: indice y coordenadas en puntos."""

    page: int
    x: float
    y: float


class Tool:
    """
    Herramienta del visor (mano, seleccionar texto, firma...). Recibe los
    eventos del lienzo con el punto ya traducido a la pagina (``hit`` es
    ``None`` fuera de las paginas) y dibuja su capa con la etiqueta ``overlay``.
    """

    cursor = ""

    def press(self, view: PageView, event, hit: PageHit | None) -> None: ...
    def drag(self, view: PageView, event, hit: PageHit | None) -> None: ...
    def release(self, view: PageView, event, hit: PageHit | None) -> None: ...
    def motion(self, view: PageView, event, hit: PageHit | None) -> None: ...
    def draw(self, view: PageView) -> None: ...


class PageView(ctk.CTkFrame):
    """Lienzo con las paginas del documento."""

    def __init__(
        self,
        master,
        *,
        continuous: bool = True,
        placeholder: tuple[str, str] = ("Abra o arrastre un PDF", ""),
        on_empty_click: Callable[[], None] | None = None,
        on_drop: Callable[[list], None] | None = None,
    ) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.continuous = continuous
        self.placeholder = placeholder
        self.on_empty_click = on_empty_click
        self.document: pymupdf.Document | None = None
        self.sizes: list[tuple[float, float]] = []
        self.layout: list[tuple[float, float, float, float]] = []
        self._tops: list[float] = []
        self.scale = BASE_SCALE
        self.zoom_mode: str | float = FIT_WIDTH if continuous else FIT_PAGE
        self.current_page = 0
        self.tool: Tool | None = None
        self.search_hits: dict[int, list[pymupdf.Rect]] = {}
        self.current_hit: tuple[int, tuple[pymupdf.Rect, ...]] | None = None
        self.selection: dict[int, list[pymupdf.Rect]] = {}
        # (pagina, mosaico o None) -> (item del lienzo, imagen, escala)
        self._displayed: dict[tuple[int, tuple[int, int] | None], tuple[int, ImageTk.PhotoImage, float]] = {}
        self._page_listeners: list[Callable[[int], None]] = []
        self._layout_listeners: list[Callable[[], None]] = []
        self._update_job: str | None = None
        self._resize_job: str | None = None
        self._last_size = (0, 0)
        self._placeholder_icon = None
        self._scrollbars_shown = (True, True)        # (horizontal, vertical)
        self._scroll_values: dict[str, tuple] = {}   # ultimo valor enviado a cada barra
        self.scheduler = RenderScheduler(self)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, background=style.themed(style.CANVAS_BG),
                                yscrollincrement=24, xscrollincrement=24, takefocus=1)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vertical = ctk.CTkScrollbar(self, orientation="vertical", command=self.canvas.yview)
        self.vertical.grid(row=0, column=1, sticky="ns", padx=(2, 0))
        self.horizontal = ctk.CTkScrollbar(self, orientation="horizontal", command=self.canvas.xview)
        self.horizontal.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        self.canvas.configure(yscrollcommand=self._on_yscroll, xscrollcommand=self._on_xscroll)

        canvas = self.canvas
        canvas.bind("<Configure>", self._on_resize)
        canvas.bind("<MouseWheel>", self._on_wheel)
        canvas.bind("<ButtonPress-1>", lambda e: self._dispatch("press", e))
        canvas.bind("<B1-Motion>", lambda e: self._dispatch("drag", e))
        canvas.bind("<ButtonRelease-1>", lambda e: self._dispatch("release", e))
        canvas.bind("<Motion>", lambda e: self._dispatch("motion", e))
        canvas.bind("<ButtonPress-2>", lambda e: canvas.scan_mark(e.x, e.y))
        canvas.bind("<B2-Motion>", lambda e: (canvas.scan_dragto(e.x, e.y, gain=1), self._schedule_update()))
        for key, action in (
            ("<Prior>", lambda: self.scroll_pages(-1)), ("<Next>", lambda: self.scroll_pages(1)),
            ("<Home>", lambda: self.go_to(0)), ("<End>", lambda: self.go_to(self.page_count - 1)),
            ("<Up>", lambda: self._scroll_units(-2)), ("<Down>", lambda: self._scroll_units(2)),
        ):
            canvas.bind(key, lambda _e, run=action: run())
        ctk.AppearanceModeTracker.add(self._on_appearance_change, canvas)
        if on_drop is not None:
            enable_file_drop(canvas, on_drop, recursive=False)
        self._draw_placeholder()

    # * Documento -----------------------------------------------------------

    @property
    def page_count(self) -> int:
        return len(self.sizes)

    def set_document(self, document: pymupdf.Document | None, page: int = 0) -> None:
        """Muestra un documento (o ninguno) a partir de ``page``."""
        self.document = document
        self.scheduler.set_document(document)
        self._displayed.clear()
        self.search_hits.clear()
        self.current_hit = None
        self.selection.clear()
        self.sizes = [(p.rect.width, p.rect.height) for p in document] if document is not None else []
        self.current_page = max(0, min(page, self.page_count - 1))
        self.zoom_mode = FIT_WIDTH if self.continuous else FIT_PAGE
        if document is None:
            self._draw_placeholder()
            self._notify_layout()
            return
        self._relayout(keep_page=self.current_page)
        self._notify_page()

    def refresh(self, pages: set[int] | None = None, page: int | None = None) -> None:
        """
        Vuelve a dibujar paginas editadas (o todas) y recalcula tamanos.
        ``pages=None`` indica un cambio de estructura (paginas giradas,
        movidas, insertadas o eliminadas): los resaltados y la seleccion de
        texto se descartan porque sus indices ya no valen. ``page`` es la
        pagina a mostrar despues (por defecto, la actual).
        """
        if self.document is None:
            return
        self.sizes = [(p.rect.width, p.rect.height) for p in self.document]
        self.scheduler.invalidate(pages)
        for key in list(self._displayed):
            if pages is None or key[0] in pages:
                self._forget_image(key)
        if pages is None:
            self.search_hits.clear()
            self.current_hit = None
            self.selection.clear()
        target = self.current_page if page is None else page
        self.current_page = max(0, min(target, self.page_count - 1))
        self._relayout(keep_page=self.current_page)
        self._notify_page()

    # * Navegacion ----------------------------------------------------------

    def go_to(self, page: int) -> None:
        if not self.sizes:
            return
        page = max(0, min(page, self.page_count - 1))
        if not self.continuous:
            if page != self.current_page:
                self.current_page = page
                self._relayout(keep_page=page)
                self._notify_page()
            return
        self._scroll_to_page(page)
        if page != self.current_page:
            self.current_page = page
            self._notify_page()

    def reveal(self, page: int, rect: pymupdf.Rect) -> None:
        """Desplaza lo minimo para que ``rect`` (de la pagina) quede a la vista, centrado si hace falta."""
        if not self.sizes:
            return
        if not self.continuous:
            self.go_to(page)
            return
        x0, y0 = self.page_to_canvas(page, rect.x0, rect.y0)
        x1, y1 = self.page_to_canvas(page, rect.x1, rect.y1)
        canvas = self.canvas
        left, top = canvas.canvasx(0), canvas.canvasy(0)
        width, height = canvas.winfo_width(), canvas.winfo_height()
        new_left, new_top = left, top
        if y0 < top + 24 or y1 > top + height - 24:
            new_top = (y0 + y1) / 2 - height / 2
        if x0 < left + 24 or x1 > left + width - 24:
            new_left = (x0 + x1) / 2 - width / 2
        if (new_left, new_top) != (left, top):
            self._scroll_canvas_to(max(new_left, 0), max(new_top, 0))
        if page != self.current_page:
            self.current_page = page
            self._notify_page()

    def scroll_pages(self, direction: int) -> None:
        if self.continuous:
            self.canvas.yview_scroll(direction, "pages")
            self._schedule_update()
        else:
            self.go_to(self.current_page + direction)

    def _scroll_units(self, units: int) -> None:
        self.canvas.yview_scroll(units, "units")
        self._schedule_update()

    def _scroll_to_page(self, page: int) -> None:
        total = self._content_height()
        if total <= 0:
            return
        top = self.layout[page][1] - GAP / 2
        self.canvas.yview_moveto(max(0.0, top / total))
        self._schedule_update()

    # * Zoom ----------------------------------------------------------------

    @property
    def zoom_percent(self) -> int:
        return round(self.scale / BASE_SCALE * 100)

    def set_zoom(self, mode: str | float, anchor: tuple[int, int] | None = None) -> None:
        """
        ``mode``: ``FIT_WIDTH``, ``FIT_PAGE`` o un porcentaje (100 = tamano
        real). ``anchor`` (pixeles del lienzo visibles) queda fijo.
        """
        if not self.sizes:
            return
        if isinstance(mode, (int, float)):
            mode = max(ZOOM_STEPS[0], min(float(mode), ZOOM_STEPS[-1]))
        hit = None
        if anchor is not None:
            hit = self.canvas_to_page(self.canvas.canvasx(anchor[0]), self.canvas.canvasy(anchor[1]))
        self.zoom_mode = mode
        self._relayout(keep_page=self.current_page if hit is None else None)
        if hit is not None:
            x, y = self.page_to_canvas(hit.page, hit.x, hit.y)
            self._scroll_canvas_to(x - anchor[0], y - anchor[1])
        debug_event("Visor", "Zoom: %s (%d%%)", mode if isinstance(mode, str) else f"{mode:.0f}%", self.zoom_percent)

    def zoom_in(self, anchor: tuple[int, int] | None = None) -> None:
        current = self.zoom_percent
        self.set_zoom(next((step for step in ZOOM_STEPS if step > current), ZOOM_STEPS[-1]), anchor)

    def zoom_out(self, anchor: tuple[int, int] | None = None) -> None:
        current = self.zoom_percent
        self.set_zoom(next((step for step in reversed(ZOOM_STEPS) if step < current), ZOOM_STEPS[0]), anchor)

    def _compute_scale(self) -> float:
        width = max(self.canvas.winfo_width(), 200)
        height = max(self.canvas.winfo_height(), 200)
        if self.zoom_mode == FIT_WIDTH:
            widest = max(size[0] for size in self.sizes) if self.continuous else self.sizes[self.current_page][0]
            return max((width - 2 * MARGIN) / widest, 0.05)
        if self.zoom_mode == FIT_PAGE:
            page_w, page_h = self.sizes[self.current_page]
            return max(min((width - 2 * MARGIN) / page_w, (height - 2 * MARGIN) / page_h), 0.05)
        return float(self.zoom_mode) / 100 * BASE_SCALE

    # * Coordenadas ---------------------------------------------------------

    def page_origin(self, page: int) -> tuple[float, float]:
        x0, y0, _x1, _y1 = self.layout[page]
        return x0, y0

    def page_rect(self, page: int) -> pymupdf.Rect:
        width, height = self.sizes[page]
        return pymupdf.Rect(0, 0, width, height)

    def page_to_canvas(self, page: int, x: float, y: float) -> tuple[float, float]:
        x0, y0 = self.page_origin(page)
        return x0 + x * self.scale, y0 + y * self.scale

    def canvas_to_page(self, canvas_x: float, canvas_y: float, clamp: bool = False) -> PageHit | None:
        """Pagina bajo un punto del lienzo (o la mas cercana con ``clamp``)."""
        if not self.layout:
            return None
        index = self._page_index_at(canvas_y) if self.continuous else self.current_page
        if index is None:
            return None
        x0, y0, x1, y1 = self.layout[index]
        if not clamp and not (x0 <= canvas_x <= x1 and y0 <= canvas_y <= y1):
            return None
        width, height = self.sizes[index]
        x = min(max((canvas_x - x0) / self.scale, 0.0), width)
        y = min(max((canvas_y - y0) / self.scale, 0.0), height)
        return PageHit(index, x, y)

    def event_to_page(self, event, clamp: bool = False) -> PageHit | None:
        return self.canvas_to_page(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y), clamp)

    def visible_pages(self) -> range:
        if not self.layout:
            return range(0)
        if not self.continuous:
            return range(self.current_page, self.current_page + 1)
        top = self.canvas.canvasy(0)
        bottom = top + self.canvas.winfo_height()
        first = max(bisect.bisect_right(self._tops, top) - 1, 0)
        last = first
        while last + 1 < len(self.layout) and self.layout[last + 1][1] <= bottom:
            last += 1
        return range(first, last + 1)

    def _page_index_at(self, canvas_y: float) -> int | None:
        if not self.continuous:
            return self.current_page
        index = max(bisect.bisect_right(self._tops, canvas_y) - 1, 0)
        _x0, y0, _x1, y1 = self.layout[index]
        if canvas_y > y1 + GAP / 2 and index + 1 < len(self.layout):
            index += 1
        return index

    # * Capas ---------------------------------------------------------------

    def set_tool(self, tool: Tool | None) -> None:
        self.tool = tool
        self.canvas.configure(cursor=tool.cursor if tool else "")
        self.redraw_overlays()

    def set_search_hits(self, hits: dict[int, list[pymupdf.Rect]],
                        current: tuple[int, tuple[pymupdf.Rect, ...]] | None = None) -> None:
        self.search_hits = hits
        self.current_hit = current
        self.redraw_overlays()

    def set_selection(self, selection: dict[int, list[pymupdf.Rect]]) -> None:
        self.selection = selection
        self.redraw_overlays()

    def redraw_overlays(self) -> None:
        canvas = self.canvas
        canvas.delete("overlay")
        if not self.layout:
            return
        visible = self.visible_pages()
        highlight = style.themed(HIGHLIGHT)
        for page in visible:
            for rect in self.search_hits.get(page, ()):
                self._draw_rect(page, rect, fill=highlight, stipple="gray50")
        if self.current_hit and self.current_hit[0] in visible:
            for rect in self.current_hit[1]:
                self._draw_rect(self.current_hit[0], rect, outline=style.themed(HIGHLIGHT_CURRENT), width=2.5, pad=2)
        selection = style.themed(SELECTION)
        for page, rects in self.selection.items():
            if page in visible:
                for rect in rects:
                    self._draw_rect(page, rect, fill=selection, stipple="gray50")
        if self.tool is not None:
            self.tool.draw(self)
        canvas.tag_raise("overlay")

    def _draw_rect(self, page: int, rect: pymupdf.Rect, pad: float = 0, **options) -> None:
        x0, y0 = self.page_to_canvas(page, rect.x0, rect.y0)
        x1, y1 = self.page_to_canvas(page, rect.x1, rect.y1)
        options.setdefault("outline", "")
        self.canvas.create_rectangle(x0 - pad, y0 - pad, x1 + pad, y1 + pad, tags="overlay", **options)

    # * Suscripciones ---------------------------------------------------------

    def on_page_changed(self, listener: Callable[[int], None]) -> None:
        self._page_listeners.append(listener)

    def on_layout_changed(self, listener: Callable[[], None]) -> None:
        self._layout_listeners.append(listener)

    def _notify_page(self) -> None:
        for listener in self._page_listeners:
            listener(self.current_page)

    def _notify_layout(self) -> None:
        for listener in self._layout_listeners:
            listener()

    # * Distribucion y dibujo -------------------------------------------------

    def _relayout(self, keep_page: int | None) -> None:
        canvas = self.canvas
        canvas.delete("all")
        self._displayed.clear()
        self.scale = self._compute_scale()
        width = max(canvas.winfo_width(), 200)
        height = max(canvas.winfo_height(), 200)
        pages = range(self.page_count) if self.continuous else [self.current_page]
        self.layout = [(0.0, 0.0, 0.0, 0.0)] * self.page_count
        widest = max((self.sizes[p][0] for p in pages), default=0) * self.scale
        y = MARGIN
        shadow, paper = style.themed(style.PAGE_SHADOW), "white"
        for page in pages:
            page_w, page_h = (value * self.scale for value in self.sizes[page])
            x = max(MARGIN, (width - page_w) / 2)
            if not self.continuous:
                y = max(MARGIN, (height - page_h) / 2)
            self.layout[page] = (x, y, x + page_w, y + page_h)
            canvas.create_rectangle(x + 3, y + 3, x + page_w + 3, y + page_h + 3, fill=shadow, outline="", tags="frame")
            canvas.create_rectangle(x, y, x + page_w, y + page_h, fill=paper, outline="", tags=("frame", f"paper{page}"))
            y += page_h + GAP
        self._tops = [self.layout[page][1] for page in range(self.page_count)] if self.continuous else []
        content_w = max(width, widest + 2 * MARGIN)
        content_h = max(height, y - GAP + MARGIN)
        canvas.configure(scrollregion=(0, 0, content_w, content_h))
        self._show_scrollbars(content_w > width + 1, content_h > height + 1)
        if keep_page is not None and self.continuous:
            self._scroll_to_page(keep_page)
        elif not self.continuous:
            canvas.xview_moveto(0)
            canvas.yview_moveto(0)
        self._update_visible()
        self._notify_layout()

    def _show_scrollbars(self, horizontal: bool, vertical: bool) -> None:
        """Muestra u oculta las barras solo si cambia (reacomodarlas cuesta un redibujo)."""
        if (horizontal, vertical) == self._scrollbars_shown:
            return
        (show if horizontal else hide)(self.horizontal)
        (show if vertical else hide)(self.vertical)
        self._scrollbars_shown = (horizontal, vertical)

    def _content_height(self) -> float:
        region = self.canvas.cget("scrollregion").split()
        return float(region[3]) if len(region) == 4 else 0.0

    def _scroll_canvas_to(self, left: float, top: float) -> None:
        region = [float(value) for value in self.canvas.cget("scrollregion").split()]
        if len(region) == 4:
            self.canvas.xview_moveto(max(0.0, left / region[2]))
            self.canvas.yview_moveto(max(0.0, top / region[3]))
        self._schedule_update()

    def _schedule_update(self) -> None:
        if self._update_job is None:
            self._update_job = self.after_idle(self._update_visible)

    def _update_visible(self) -> None:
        self._update_job = None
        if not self.layout:
            return
        visible = self.visible_pages()
        if self.continuous and visible:
            center = self.canvas.canvasy(0) + self.canvas.winfo_height() / 3
            page = self._page_index_at(center)
            if page is not None and page != self.current_page:
                self.current_page = page
                self._notify_page()
        wanted = range(max(visible.start - 1, 0), min(visible.stop + 1, self.page_count))
        scale = self.scale
        current_key = scale_key(scale)
        wanted_tiles: set[tuple[int, tuple[int, int] | None]] = set()
        for page in wanted:
            priority = abs(page - self.current_page) + (0 if page in visible else 0.5)
            if not self._uses_tiles(page):
                wanted_tiles.add((page, None))
                entry = self._displayed.get((page, None))
                if entry is None or entry[2] != current_key:
                    self.scheduler.request(page, scale, self._place_image, priority)
            elif page in visible:  # con zoom alto solo se dibuja lo que se ve
                for tile, clip in self._visible_tiles(page):
                    wanted_tiles.add((page, tile))
                    entry = self._displayed.get((page, tile))
                    if entry is None or entry[2] != current_key:
                        self.scheduler.request(page, scale, self._place_image, priority, tile=tile, clip=clip)
        self.scheduler.cancel_where(lambda p, s, t: s == scale_key(self.scale) and (p, t) in wanted_tiles,
                                    callback=self._place_image)
        for key in list(self._displayed):
            page, tile = key
            far = page < visible.start - KEEP_RENDERED or page >= visible.stop + KEEP_RENDERED
            if far or (tile is not None and key not in wanted_tiles):
                self._forget_image(key)
        self.redraw_overlays()

    def _uses_tiles(self, page: int) -> bool:
        width, height = self.sizes[page]
        return width * height * self.scale * self.scale > TILE_THRESHOLD_PX

    def _visible_tiles(self, page: int):
        """Mosaicos de la pagina que se ven (con medio mosaico de margen) y su recorte en puntos."""
        x0, y0, x1, y1 = self.layout[page]
        canvas = self.canvas
        margin = TILE_PX / 2
        left, top = canvas.canvasx(0) - margin, canvas.canvasy(0) - margin
        right, bottom = left + canvas.winfo_width() + 2 * margin, top + canvas.winfo_height() + 2 * margin
        width, height = self.sizes[page]
        columns = int((x1 - x0 + TILE_PX - 1) // TILE_PX)
        rows = int((y1 - y0 + TILE_PX - 1) // TILE_PX)
        for row in range(rows):
            tile_top = y0 + row * TILE_PX
            if tile_top > bottom or tile_top + TILE_PX < top:
                continue
            for column in range(columns):
                tile_left = x0 + column * TILE_PX
                if tile_left > right or tile_left + TILE_PX < left:
                    continue
                clip = pymupdf.Rect(
                    column * TILE_PX / self.scale, row * TILE_PX / self.scale,
                    min((column + 1) * TILE_PX / self.scale, width), min((row + 1) * TILE_PX / self.scale, height),
                )
                yield (column, row), clip

    def _place_image(self, page: int, scale: float, photo: ImageTk.PhotoImage, tile=None) -> None:
        if scale_key(scale) != scale_key(self.scale) or page >= len(self.layout) or self.layout[page][2] == 0:
            return
        key = (page, tile)
        self._forget_image(key)
        x0, y0, _x1, _y1 = self.layout[page]
        if tile is not None:
            x0, y0 = x0 + tile[0] * TILE_PX, y0 + tile[1] * TILE_PX
        item = self.canvas.create_image(x0, y0, anchor="nw", image=photo, tags=("page", f"img{page}"))
        self._displayed[key] = (item, photo, scale_key(scale))
        self.canvas.tag_raise("overlay")

    def _forget_image(self, key) -> None:
        entry = self._displayed.pop(key, None)
        if entry is not None:
            self.canvas.delete(entry[0])

    # * Eventos ---------------------------------------------------------------

    def _on_yscroll(self, first, last) -> None:
        if self._scroll_values.get("y") != (first, last):  # CTkScrollbar redibuja en cada set
            self._scroll_values["y"] = (first, last)
            self.vertical.set(first, last)
        self._schedule_update()

    def _on_xscroll(self, first, last) -> None:
        if self._scroll_values.get("x") != (first, last):
            self._scroll_values["x"] = (first, last)
            self.horizontal.set(first, last)

    def _on_resize(self, event) -> None:
        size = (event.width, event.height)
        if size == self._last_size:
            return
        self._last_size = size
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(RESIZE_DEBOUNCE_MS, self._apply_resize)

    def _apply_resize(self) -> None:
        self._resize_job = None
        if self.document is None:
            self._draw_placeholder()
        else:
            self._relayout(keep_page=self.current_page)

    def _on_wheel(self, event) -> None:
        if not self.sizes:
            return
        if event.state & 0x0004:  # Ctrl: zoom con el punto bajo el cursor fijo
            (self.zoom_in if event.delta > 0 else self.zoom_out)(anchor=(event.x, event.y))
        elif event.state & 0x0001:  # Shift: horizontal
            self.canvas.xview_scroll(-2 if event.delta > 0 else 2, "units")
        elif self.continuous:
            self._scroll_units(-3 if event.delta > 0 else 3)
        else:
            self.canvas.yview_scroll(-3 if event.delta > 0 else 3, "units")

    def _dispatch(self, kind: str, event) -> None:
        if kind == "press":
            self.canvas.focus_set()
        if self.document is None:
            if kind == "press" and self.on_empty_click:
                self.on_empty_click()
            return
        if self.tool is not None:
            getattr(self.tool, kind)(self, event, self.event_to_page(event, clamp=kind != "motion"))

    def _on_appearance_change(self, mode: str) -> None:
        self.canvas.configure(background=style.CANVAS_BG[1] if mode.lower() == "dark" else style.CANVAS_BG[0])
        if self.document is None:
            self._draw_placeholder()
        else:
            self._relayout(keep_page=self.current_page)

    # * Sin documento ---------------------------------------------------------

    def _draw_placeholder(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        self.layout = []
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 50 or height < 50:
            width, height = 640, 480
        canvas.configure(scrollregion=(0, 0, width, height))
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)
        self._show_scrollbars(False, False)
        scaling = ctk.ScalingTracker.get_widget_scaling(self)
        muted = style.themed(style.TEXT_MUTED)
        inset = 16
        text_width = max(width - 2 * inset - 40, 200)
        canvas.create_rectangle(inset, inset, width - inset, height - inset, outline=muted, dash=(6, 5), width=1.5)
        center_x, center_y = width / 2, height / 2
        icon = render_glyph(GLYPHS["pdf"], round(52 * scaling), muted)
        if icon is not None:
            self._placeholder_icon = ImageTk.PhotoImage(icon.resize((round(52 * scaling),) * 2))
            canvas.create_image(center_x, center_y - 34 * scaling, image=self._placeholder_icon, anchor="center")
        title, subtitle = self.placeholder
        canvas.create_text(center_x, center_y + 14 * scaling, text=title, anchor="center", justify="center",
                           width=text_width, fill=style.themed(style.TEXT),
                           font=(style.FONT_FAMILY, round(13 * scaling), "bold"))
        canvas.create_text(center_x, center_y + 40 * scaling, text=subtitle, anchor="center", justify="center",
                           width=text_width, fill=muted, font=(style.FONT_FAMILY, round(10 * scaling)))

    def set_placeholder(self, title: str, subtitle: str) -> None:
        self.placeholder = (title, subtitle)
        if self.document is None:
            self._draw_placeholder()
