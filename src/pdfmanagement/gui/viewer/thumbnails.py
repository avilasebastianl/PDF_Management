"""
Panel de miniaturas: navegacion rapida por paginas.

Comparte el ``RenderScheduler`` del visor (con menor prioridad) y solo dibuja
las miniaturas visibles, asi un PDF de cientos de paginas no frena nada.
"""

import bisect
import tkinter as tk

import customtkinter as ctk
from PIL import ImageTk

from .. import style
from .page_view import PageView
from .render import scale_key

THUMB_WIDTH = 120
PADDING = 14
LABEL_HEIGHT = 18
THUMB_PRIORITY = 100  # despues de las paginas visibles del visor


class ThumbnailStrip(ctk.CTkFrame):
    """Lista vertical de miniaturas sincronizada con un ``PageView``."""

    def __init__(self, master, view: PageView) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.view = view
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, background=style.themed(style.CARD_BG),
                                width=THUMB_WIDTH + 2 * PADDING, yscrollincrement=20)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ctk.CTkScrollbar(self, orientation="vertical", command=self.canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=lambda a, b: (scrollbar.set(a, b), self._schedule()))
        self.canvas.bind("<Configure>", lambda _e: self._schedule())
        self.canvas.bind("<MouseWheel>", lambda e: (self.canvas.yview_scroll(-3 if e.delta > 0 else 3, "units"), self._schedule()))
        self.canvas.bind("<ButtonPress-1>", self._on_click)
        ctk.AppearanceModeTracker.add(self._on_appearance_change, self.canvas)
        self._slots: list[tuple[float, float, float, float, float]] = []  # x0, y0, x1, y1, escala
        self._tops: list[float] = []
        self._images: dict[int, tuple[int, ImageTk.PhotoImage]] = {}
        self._job: str | None = None
        view.on_page_changed(self._on_page_changed)
        view.on_layout_changed(self._on_layout_changed)

    def _on_layout_changed(self) -> None:
        if len(self._slots) != self.view.page_count:
            self.rebuild()

    def rebuild(self) -> None:
        """Recalcula las ranuras (al abrir otro documento o editar paginas)."""
        canvas = self.canvas
        canvas.delete("all")
        self._images.clear()
        self._slots = []
        y = PADDING
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
            canvas.create_rectangle(x, y, x + thumb_w, y + thumb_h, fill="white", outline=style.themed(style.CARD_BORDER),
                                    tags=("slot", f"slot{page}"))
            canvas.create_text(PADDING + THUMB_WIDTH / 2, y + thumb_h + 4, text=str(page + 1), anchor="n",
                               fill=muted, font=(style.FONT_FAMILY, 9), tags="label")
            y += thumb_h + LABEL_HEIGHT + PADDING
        self._tops = [slot[1] for slot in self._slots]
        canvas.configure(scrollregion=(0, 0, THUMB_WIDTH + 2 * PADDING, y))
        canvas.yview_moveto(0)
        self._highlight(self.view.current_page)
        self._schedule()

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
            if page not in self._images:
                self.view.scheduler.request(page, self._slots[page][4], self._place, THUMB_PRIORITY + page - first)
            page += 1

    def _place(self, page: int, scale: float, photo: ImageTk.PhotoImage, _tile=None) -> None:
        if page >= len(self._slots) or scale_key(scale) != scale_key(self._slots[page][4]) or page in self._images:
            return
        x0, y0, *_ = self._slots[page]
        item = self.canvas.create_image(x0, y0, anchor="nw", image=photo, tags="thumb")
        self._images[page] = (item, photo)
        self.canvas.tag_raise("current")

    def _on_click(self, event) -> None:
        y = self.canvas.canvasy(event.y)
        page = max(bisect.bisect_right(self._tops, y) - 1, 0)
        if self._slots and self._slots[page][1] <= y <= self._slots[page][3] + LABEL_HEIGHT:
            self.view.go_to(page)

    def _on_page_changed(self, page: int) -> None:
        self._highlight(page)
        if page < len(self._slots):
            _x0, y0, _x1, y1, _scale = self._slots[page]
            top = self.canvas.canvasy(0)
            bottom = top + self.canvas.winfo_height()
            region = float(self.canvas.cget("scrollregion").split()[3] or 1)
            if y0 < top or y1 > bottom:  # mantener visible la miniatura actual
                self.canvas.yview_moveto(max(0.0, (y0 - PADDING) / region))

    def _highlight(self, page: int) -> None:
        self.canvas.delete("current")
        if page < len(self._slots):
            x0, y0, x1, y1, _scale = self._slots[page]
            self.canvas.create_rectangle(x0 - 4, y0 - 4, x1 + 4, y1 + 4, outline=style.themed(style.accent_color()),
                                         width=3, tags="current")

    def _on_appearance_change(self, mode: str) -> None:
        self.canvas.configure(background=style.CARD_BG[1] if mode.lower() == "dark" else style.CARD_BG[0])
        if self._slots:
            images = dict(self._images)
            self.rebuild()
            for page, (_item, photo) in images.items():
                self._place(page, self._slots[page][4], photo)
