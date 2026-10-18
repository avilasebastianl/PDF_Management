"""
Panel de miniaturas: navegacion rapida y organizacion de paginas.

Comparte el ``RenderScheduler`` del visor (con menor prioridad) y solo dibuja
las miniaturas visibles, asi un PDF de cientos de paginas no frena nada.

Seleccion como en el Explorador de Windows: clic selecciona una pagina (y la
muestra), Ctrl+clic agrega o quita, Mayus+clic selecciona un rango. Si hay un
``on_move``, arrastrar miniaturas las reordena (una linea indica donde caeran)
y el panel se desplaza solo al acercarse a los bordes.
"""

import bisect
import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk
from PIL import ImageTk

from .. import style
from .page_view import PageView
from .render import scale_key
from .wheel import WheelSteps

THUMB_WIDTH = 120
PADDING = 14
LABEL_HEIGHT = 18
THUMB_PRIORITY = 100  # despues de las paginas visibles del visor
DRAG_THRESHOLD = 6  # pixeles antes de considerar que el clic es un arrastre
AUTOSCROLL_MARGIN = 28
AUTOSCROLL_MS = 40

CTRL_MASK = 0x0004
SHIFT_MASK = 0x0001


class ThumbnailStrip(ctk.CTkFrame):
    """Lista vertical de miniaturas sincronizada con un ``PageView``."""

    def __init__(
        self,
        master,
        view: PageView,
        *,
        on_move: Callable[[list[int], int], None] | None = None,
        on_context: Callable[[int, object], None] | None = None,
        on_selection: Callable[[list[int]], None] | None = None,
    ) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.view = view
        self.on_move = on_move  # (paginas, destino): soltar delante de ``destino``
        self.on_context = on_context  # (pagina, evento): clic derecho
        self.on_selection = on_selection
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(
            self,
            highlightthickness=0,
            background=style.themed(style.CARD_BG),
            width=THUMB_WIDTH + 2 * PADDING,
            yscrollincrement=20,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ctk.CTkScrollbar(self, orientation="vertical", command=self.canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self._scrollbar = scrollbar
        self.canvas.configure(yscrollcommand=self._on_yscroll)
        self.canvas.bind("<Configure>", lambda _e: self._schedule())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<TouchpadScroll>", self._on_touchpad)
        self._wheel = WheelSteps()
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<ButtonPress-3>", self._on_right_click)
        ctk.AppearanceModeTracker.add(self._on_appearance_change, self.canvas)
        self._slots: list[tuple[float, float, float, float, float]] = []  # x0, y0, x1, y1, escala
        self._tops: list[float] = []
        self._images: dict[int, tuple[int, ImageTk.PhotoImage]] = {}
        self._stale: set[int] = set()  # miniaturas que se redibujan (la vieja se ve mientras)
        self._job: str | None = None
        self.selected: set[int] = set()
        self._anchor = 0  # inicio de los rangos con Mayus
        self._press: tuple[int, float, bool] | None = None  # pagina, y, seleccion pendiente al soltar
        self.dragging = False
        self._drop_target: int | None = None
        self._autoscroll_job: str | None = None
        self._pointer_y = 0
        view.on_page_changed(self._on_page_changed)
        view.on_layout_changed(self._on_layout_changed)

    def _on_yscroll(self, first, last) -> None:
        self._scrollbar.set(first, last)
        self._schedule()

    def _on_wheel(self, event) -> None:
        self._scroll(self._wheel.wheel(event.delta))

    def _on_touchpad(self, event) -> None:
        self._scroll(self._wheel.touchpad(self.canvas, event.delta)[1])

    def _scroll(self, rows: int) -> None:
        if rows:
            self.canvas.yview_scroll(rows, "units")
            self._schedule()

    def _on_layout_changed(self) -> None:
        if len(self._slots) != self.view.page_count:
            self.rebuild(keep_scroll=True)

    def rebuild(self, keep_scroll: bool = False) -> None:
        """Recalcula las ranuras (al abrir otro documento o editar paginas)."""
        canvas = self.canvas
        top = canvas.yview()[0] if keep_scroll else 0.0
        canvas.delete("all")
        self._images.clear()
        self._stale.clear()
        self._slots = []
        self.selected = {page for page in self.selected if page < self.view.page_count}
        y: float = PADDING
        muted = style.themed(style.TEXT_MUTED)
        for page, (width, height) in enumerate(self.view.sizes):
            scale = THUMB_WIDTH / width
            thumb_h = height * scale
            if thumb_h > THUMB_WIDTH * 1.6:  # paginas muy altas: limitar por alto
                scale = THUMB_WIDTH * 1.6 / height
                thumb_h = height * scale
            thumb_w = width * scale
            x = PADDING + (THUMB_WIDTH - thumb_w) / 2
            self._slots.append((x, y, x + thumb_w, y + thumb_h, scale))
            canvas.create_rectangle(
                x,
                y,
                x + thumb_w,
                y + thumb_h,
                fill="white",
                outline=style.themed(style.CARD_BORDER),
                tags=("slot", f"slot{page}"),
            )
            canvas.create_text(
                PADDING + THUMB_WIDTH / 2,
                y + thumb_h + 4,
                text=str(page + 1),
                anchor="n",
                fill=muted,
                font=(style.FONT_FAMILY, 9),
                tags="label",
            )
            y += thumb_h + LABEL_HEIGHT + PADDING
        self._tops = [slot[1] for slot in self._slots]
        canvas.configure(scrollregion=(0, 0, THUMB_WIDTH + 2 * PADDING, y))
        canvas.yview_moveto(top)
        self._draw_selection()
        self._highlight(self.view.current_page)
        self._schedule()

    def refresh_pages(self, pages) -> None:
        """Vuelve a dibujar las miniaturas cuyo contenido cambio (p. ej. al anotar)."""
        self._stale.update(page for page in pages if page in self._images)
        self._schedule()

    # * Dibujo --------------------------------------------------------------

    def _schedule(self) -> None:
        if self._job is None:
            self._job = self.after_idle(self._render_visible)

    def _render_visible(self) -> None:
        self._job = None
        if not self._slots:
            return
        top = self.canvas.canvasy(0)
        bottom = top + self.canvas.winfo_height()
        first = max(bisect.bisect_right(self._tops, top) - 1, 0)
        page = first
        while page < len(self._slots) and self._slots[page][1] <= bottom:
            if page not in self._images or page in self._stale:
                self.view.scheduler.request(page, self._slots[page][4], self._place, THUMB_PRIORITY + page - first)
            page += 1

    def _place(self, page: int, scale: float, photo: ImageTk.PhotoImage, _tile=None) -> None:
        if page >= len(self._slots) or scale_key(scale) != scale_key(self._slots[page][4]):
            return
        if page in self._images:
            if page not in self._stale:
                return
            self.canvas.delete(self._images.pop(page)[0])
        self._stale.discard(page)
        x0, y0, *_ = self._slots[page]
        item = self.canvas.create_image(x0, y0, anchor="nw", image=photo, tags="thumb")
        self._images[page] = (item, photo)
        self.canvas.tag_raise("current")
        self.canvas.tag_raise("drop")

    def _highlight(self, page: int) -> None:
        self.canvas.delete("current")
        if page < len(self._slots):
            x0, y0, x1, y1, _scale = self._slots[page]
            self.canvas.create_rectangle(
                x0 - 4, y0 - 4, x1 + 4, y1 + 4, outline=style.themed(style.accent_color()), width=3, tags="current"
            )

    def _draw_selection(self) -> None:
        """Fondo resaltado detras de las paginas seleccionadas (si hay mas de una o difiere de la actual)."""
        canvas = self.canvas
        canvas.delete("selected")
        if self.selected == {self.view.current_page}:
            return  # la pagina actual ya tiene su borde
        fill = style.themed(style.HOVER)
        accent = style.themed(style.accent_color())
        for page in sorted(self.selected):
            if page < len(self._slots):
                _x0, y0, _x1, y1, _scale = self._slots[page]
                canvas.create_rectangle(
                    PADDING - 8,
                    y0 - 8,
                    PADDING + THUMB_WIDTH + 8,
                    y1 + LABEL_HEIGHT + 2,
                    fill=fill,
                    outline=accent,
                    width=1,
                    tags="selected",
                )
        canvas.tag_lower("selected")

    # * Seleccion -----------------------------------------------------------

    def set_selection(self, pages, anchor: int | None = None) -> None:
        self.selected = {page for page in pages if 0 <= page < len(self._slots)}
        if anchor is not None:
            self._anchor = anchor
        self._draw_selection()
        if self.on_selection:
            self.on_selection(sorted(self.selected))

    def selection(self) -> list[int]:
        """Paginas seleccionadas o, si no hay, la actual."""
        return sorted(self.selected) if self.selected else [self.view.current_page]

    def _page_at(self, canvas_y: float) -> int | None:
        if not self._slots:
            return None
        page = max(bisect.bisect_right(self._tops, canvas_y) - 1, 0)
        _x0, y0, _x1, y1, _scale = self._slots[page]
        return page if y0 - PADDING / 2 <= canvas_y <= y1 + LABEL_HEIGHT + PADDING / 2 else None

    def _select_click(self, page: int, state: int) -> None:
        if state & SHIFT_MASK:
            low, high = sorted((self._anchor, page))
            pages = set(range(low, high + 1)) | (self.selected if state & CTRL_MASK else set())
            self.set_selection(pages)
        elif state & CTRL_MASK:
            self.set_selection(self.selected ^ {page}, anchor=page)
        else:
            self.set_selection({page}, anchor=page)
        self.view.go_to(page)

    # * Raton ---------------------------------------------------------------

    def _on_press(self, event) -> None:
        self.canvas.focus_set()
        page = self._page_at(self.canvas.canvasy(event.y))
        if page is None:
            self._press = None
            return
        # Sobre una pagina ya seleccionada se espera a soltar: puede ser el
        # comienzo de un arrastre de toda la seleccion.
        deferred = page in self.selected and not event.state & (CTRL_MASK | SHIFT_MASK)
        self._press = (page, event.y, deferred)
        if not deferred:
            self._select_click(page, event.state)

    def _on_drag(self, event) -> None:
        if self._press is None or self.on_move is None:
            return
        self._pointer_y = event.y
        if not self.dragging:
            if abs(event.y - self._press[1]) < DRAG_THRESHOLD:
                return
            self.dragging = True
            if self._press[0] not in self.selected:
                self.set_selection({self._press[0]}, anchor=self._press[0])
            self.canvas.configure(cursor="fleur")
            self._autoscroll()
        self._show_drop(self._drop_index(self.canvas.canvasy(event.y)))

    def _on_release(self, event) -> None:
        press, self._press = self._press, None
        if self.dragging:
            self.dragging = False
            self.canvas.configure(cursor="")
            self.canvas.delete("drop")
            if self._autoscroll_job:
                self.after_cancel(self._autoscroll_job)
                self._autoscroll_job = None
            target = self._drop_target
            self._drop_target = None
            if target is not None and self.on_move:
                self.on_move(sorted(self.selected), target)
            return
        if press is not None and press[2]:  # clic simple sobre una pagina ya seleccionada
            self._select_click(press[0], 0)

    def _on_right_click(self, event) -> None:
        page = self._page_at(self.canvas.canvasy(event.y))
        if page is None or self.on_context is None:
            return
        if page not in self.selected:
            self._select_click(page, 0)
        self.on_context(page, event)

    def _drop_index(self, canvas_y: float) -> int:
        """Indice delante del cual caerian las paginas (``page_count`` = al final)."""
        for page, (_x0, y0, _x1, y1, _scale) in enumerate(self._slots):
            if canvas_y < (y0 + y1) / 2:
                return page
        return len(self._slots)

    def _show_drop(self, target: int) -> None:
        if target == self._drop_target:
            return
        self._drop_target = target
        self.canvas.delete("drop")
        if target < len(self._slots):
            y = self._slots[target][1] - PADDING / 2
        else:
            y = self._slots[-1][3] + LABEL_HEIGHT + PADDING / 2
        accent = style.themed(style.accent_color())
        self.canvas.create_line(PADDING - 6, y, PADDING + THUMB_WIDTH + 6, y, fill=accent, width=3, tags="drop")
        self.canvas.create_oval(PADDING - 10, y - 4, PADDING - 2, y + 4, fill=accent, outline=accent, tags="drop")

    def _autoscroll(self) -> None:
        """Mientras se arrastra cerca de un borde, el panel se desplaza solo."""
        self._autoscroll_job = None
        if not self.dragging:
            return
        height = self.canvas.winfo_height()
        step = -1 if self._pointer_y < AUTOSCROLL_MARGIN else 1 if self._pointer_y > height - AUTOSCROLL_MARGIN else 0
        if step:
            self.canvas.yview_scroll(step, "units")
            self._show_drop(self._drop_index(self.canvas.canvasy(self._pointer_y)))
            self._schedule()
        self._autoscroll_job = self.after(AUTOSCROLL_MS, self._autoscroll)

    # * Visor ---------------------------------------------------------------

    def _on_page_changed(self, page: int) -> None:
        self._highlight(page)
        self._draw_selection()
        if page < len(self._slots) and not self.dragging:
            _x0, y0, _x1, y1, _scale = self._slots[page]
            top = self.canvas.canvasy(0)
            bottom = top + self.canvas.winfo_height()
            region = float(self.canvas.cget("scrollregion").split()[3] or 1)
            if y0 < top or y1 > bottom:  # mantener visible la miniatura actual
                self.canvas.yview_moveto(max(0.0, (y0 - PADDING) / region))

    def _on_appearance_change(self, mode: str) -> None:
        self.canvas.configure(background=style.CARD_BG[1] if mode.lower() == "dark" else style.CARD_BG[0])
        if self._slots:
            images = dict(self._images)
            self.rebuild(keep_scroll=True)
            for page, (_item, photo) in images.items():
                self._place(page, self._slots[page][4], photo)
