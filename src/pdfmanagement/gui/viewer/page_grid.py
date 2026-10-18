"""
Cuadricula de paginas para organizar un PDF (seccion Organizar).

Cada pagina es una tarjeta con su miniatura, su numero y una casilla. Al pasar
el cursor o seleccionarla aparecen girar a la izquierda, a la derecha y
eliminar. Entre las tarjetas hay botones ``+`` para insertar paginas. Las
tarjetas se arrastran para cambiar el orden (con varias seleccionadas se mueven
todas juntas).

Todo se dibuja en un ``tk.Canvas``: las tarjetas son rectangulos y las
miniaturas se piden al ``RenderScheduler`` solo para las filas visibles, asi
un documento de cientos de paginas abre y se desplaza sin demoras.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import customtkinter as ctk
import pymupdf
from PIL import Image, ImageTk

from ...i18n import tr
from .. import style
from ..icons import GLYPHS, render_glyph
from ..widgets import enable_file_drop
from .render import RenderScheduler, scale_key
from .wheel import WheelSteps

THUMB = 150  # ancho de la miniatura (pixeles logicos)
THUMB_RATIO = 1.42  # alto del recuadro de la miniatura respecto del ancho (A4 vertical)
PAD = 12  # margen interno de la tarjeta
GAP = 44  # espacio entre tarjetas (alli va el boton +)
ROW_GAP = 18
MARGIN = 24
LABEL_H = 26  # numero de pagina
ACTIONS_H = 32  # fila de girar / eliminar
CHECK = 16  # casilla de seleccion
PLUS_R = 13  # radio del boton +
ICON = 16
DRAG_THRESHOLD = 6
AUTOSCROLL_MARGIN = 30


class PageGrid(ctk.CTkFrame):
    """Cuadricula de miniaturas con seleccion, arrastrar y soltar y acciones por pagina."""

    def __init__(
        self,
        master,
        *,
        on_rotate: Callable[[list[int], int], None],
        on_delete: Callable[[list[int]], None],
        on_move: Callable[[list[int], int], None],
        on_insert: Callable[[int, int, int], None],
        on_selection: Callable[[list[int]], None] | None = None,
        on_empty_click: Callable[[], None] | None = None,
        on_drop: Callable[[list], None] | None = None,
    ) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.on_rotate = on_rotate
        self.on_delete = on_delete
        self.on_move = on_move
        self.on_insert = on_insert
        self.on_selection = on_selection or (lambda _pages: None)
        self.on_empty_click = on_empty_click
        self.document: pymupdf.Document | None = None
        self.selected: set[int] = set()
        self.anchor: int | None = None
        self.hover: int | None = None
        self._cells: list[tuple[float, float]] = []  # esquina de cada tarjeta
        self._columns = 1
        self._images: dict[int, tuple[int, ImageTk.PhotoImage, float]] = {}
        self._press: tuple[int, int, int | None] | None = None  # x, y y pagina bajo el clic
        self._dragging = False
        self._drop_index: int | None = None
        self._update_job: str | None = None
        self._wheel = WheelSteps()
        self.scheduler = RenderScheduler(self)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, yscrollincrement=20, takefocus=1)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = ctk.CTkScrollbar(self, orientation="vertical", command=self._yview)
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        canvas = self.canvas
        canvas.bind("<Configure>", lambda _e: self.redraw())
        canvas.bind("<ButtonPress-1>", self._on_press)
        canvas.bind("<B1-Motion>", self._on_drag)
        canvas.bind("<ButtonRelease-1>", self._on_release)
        canvas.bind("<Motion>", self._on_motion)
        canvas.bind("<Leave>", lambda _e: self._set_hover(None))
        canvas.bind("<MouseWheel>", lambda e: self._scroll(self._wheel.wheel(e.delta)))
        canvas.bind("<TouchpadScroll>", lambda e: self._scroll(self._wheel.touchpad(canvas, e.delta)[1]))
        ctk.AppearanceModeTracker.add(self._on_appearance_change, canvas)
        if on_drop is not None:
            enable_file_drop(canvas, on_drop, recursive=False)
        self._icons: dict[tuple[str, bool], ImageTk.PhotoImage] = {}
        self.hint = ""  # descripcion de lo que hay bajo el cursor (la seccion la muestra)
        self.on_hint: Callable[[str], None] = lambda _text: None

    def _on_appearance_change(self, _mode: str) -> None:
        self._icons.clear()  # los iconos llevan el color del tema
        self.redraw()

    # * Documento -------------------------------------------------------------

    def set_document(self, document: pymupdf.Document | None) -> None:
        self.document = document
        self.scheduler.set_document(document)
        self.selected.clear()
        self.anchor = self.hover = None
        self.canvas.yview_moveto(0)
        self.redraw()
        self.on_selection([])

    def refresh(self, select: list[int] | None = None) -> None:
        """Tras editar: vuelve a dibujar todo (paginas giradas, movidas, insertadas o eliminadas)."""
        self.scheduler.invalidate()
        count = self.page_count
        if select is not None:
            self.selected = {page for page in select if 0 <= page < count}
        else:
            self.selected = {page for page in self.selected if page < count}
        self.redraw()
        self.on_selection(self.selection())

    @property
    def page_count(self) -> int:
        return self.document.page_count if self.document is not None else 0

    def selection(self) -> list[int]:
        return sorted(self.selected)

    def set_selection(self, pages: list[int]) -> None:
        self.selected = {page for page in pages if 0 <= page < self.page_count}
        self._update_cards()
        self.on_selection(self.selection())

    def select_all(self) -> None:
        self.set_selection(list(range(self.page_count)))

    # * Geometria ---------------------------------------------------------------

    def _scaled(self, value: float) -> float:
        return value * ctk.ScalingTracker.get_widget_scaling(self)

    def _metrics(self) -> dict[str, float]:
        thumb = self._scaled(THUMB)
        pad = self._scaled(PAD)
        card_w = thumb + 2 * pad
        box_h = thumb * THUMB_RATIO
        card_h = pad + box_h + self._scaled(LABEL_H) + self._scaled(ACTIONS_H)
        return {
            "thumb": thumb,
            "box_h": box_h,
            "pad": pad,
            "card_w": card_w,
            "card_h": card_h,
            "gap": self._scaled(GAP),
            "row_gap": self._scaled(ROW_GAP),
            "margin": self._scaled(MARGIN),
        }

    def _layout(self) -> dict[str, float]:
        m = self._metrics()
        width = max(self.canvas.winfo_width(), 200)
        columns = max(1, int((width - 2 * m["margin"] + m["gap"]) // (m["card_w"] + m["gap"])))
        used = columns * m["card_w"] + (columns - 1) * m["gap"]
        left = max(m["margin"], (width - used) / 2)
        self._columns = columns
        self._cells = []
        for page in range(self.page_count):
            row, column = divmod(page, columns)
            x = left + column * (m["card_w"] + m["gap"])
            y = m["margin"] + row * (m["card_h"] + m["row_gap"])
            self._cells.append((x, y))
        rows = (self.page_count + columns - 1) // columns
        m["height"] = 2 * m["margin"] + rows * m["card_h"] + max(rows - 1, 0) * m["row_gap"]
        return m

    # * Dibujo ---------------------------------------------------------------------

    def redraw(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        self._images.clear()
        canvas.configure(background=style.themed(style.CARD_BG))
        if self.document is None or not self.page_count:
            self._draw_empty()
            return
        m = self._layout()
        canvas.configure(scrollregion=(0, 0, canvas.winfo_width(), max(m["height"], canvas.winfo_height())))
        text, muted = style.themed(style.TEXT), style.themed(style.TEXT_MUTED)
        border = style.themed(style.CARD_BORDER)
        font = (style.FONT_FAMILY, round(self._scaled(10)))
        for page, (x, y) in enumerate(self._cells):
            card = f"card{page}"
            canvas.create_rectangle(
                x, y, x + m["card_w"], y + m["card_h"], fill="", outline="", width=0, tags=(card, f"bg{page}", "bg")
            )
            # Recuadro de la hoja (se ve mientras llega la miniatura).
            box = self._box(page, m)
            canvas.create_rectangle(*box, fill="white", outline=border, tags=(card, f"paper{page}"))
            canvas.create_text(
                x + m["card_w"] / 2,
                y + m["pad"] + m["box_h"] + self._scaled(LABEL_H) / 2,
                text=str(page + 1),
                fill=text,
                font=font,
                tags=(card, f"num{page}"),
            )
            # Casilla de seleccion (arriba a la izquierda).
            check = self._scaled(CHECK)
            cx, cy = x + self._scaled(6), y + self._scaled(6)
            canvas.create_rectangle(
                cx,
                cy,
                cx + check,
                cy + check,
                fill=style.themed(style.CARD_BG),
                outline=muted,
                tags=(f"chk{page}", f"chkbox{page}", "chk"),
            )
            # Marca dibujada como linea (el caracter de "check" no existe en todas las fuentes).
            canvas.create_line(
                [
                    cx + check * 0.22,
                    cy + check * 0.52,
                    cx + check * 0.42,
                    cy + check * 0.72,
                    cx + check * 0.80,
                    cy + check * 0.30,
                ],
                width=max(2.0, self._scaled(2)),
                capstyle="round",
                joinstyle="round",
                state="hidden",
                tags=(f"chk{page}", f"tick{page}", "chk"),
            )
            # Girar y eliminar (visibles al pasar el cursor o con la pagina seleccionada).
            ay = y + m["pad"] + m["box_h"] + self._scaled(LABEL_H) + self._scaled(ACTIONS_H) / 2
            for offset, action in ((-1, "rotl"), (0, "rotr"), (1, "del")):
                canvas.create_image(
                    x + m["card_w"] / 2 + offset * self._scaled(30),
                    ay,
                    image=self._icon(action, False),
                    state="hidden",
                    tags=(f"{action}{page}", f"act{page}", "action"),
                )
        self._draw_plus_buttons(m)
        self._update_cards()
        self._schedule_update()

    def _box(self, page: int, m: dict[str, float]) -> tuple[float, float, float, float]:
        """Rectangulo de la miniatura de ``page``, centrado en su recuadro y con su proporcion."""
        x, y = self._cells[page]
        rect = self.document[page].rect if self.document is not None else pymupdf.Rect(0, 0, 595, 842)
        scale = min(m["thumb"] / rect.width, m["box_h"] / rect.height)
        width, height = rect.width * scale, rect.height * scale
        left = x + m["pad"] + (m["thumb"] - width) / 2
        top = y + m["pad"] + (m["box_h"] - height) / 2
        return left, top, left + width, top + height

    def _draw_plus_buttons(self, m: dict[str, float]) -> None:
        """Un ``+`` antes de cada tarjeta y otro despues de la ultima de cada fila."""
        canvas = self.canvas
        radius = self._scaled(PLUS_R)
        fill, outline = style.themed(style.ROW_BG), style.themed(style.CARD_BORDER)
        text = style.themed(style.TEXT)
        font = (style.FONT_FAMILY, round(self._scaled(12)), "bold")
        spots: list[tuple[int, float, float]] = []
        for page, (x, y) in enumerate(self._cells):
            center_y = y + m["pad"] + m["box_h"] / 2
            spots.append((page, x - m["gap"] / 2, center_y))
            last_in_row = (page + 1) % self._columns == 0 or page == self.page_count - 1
            if last_in_row:
                spots.append((page + 1, x + m["card_w"] + m["gap"] / 2, center_y))
        for index, cx, cy in spots:
            tag = f"plus{index}"
            canvas.create_oval(
                cx - radius, cy - radius, cx + radius, cy + radius, fill=fill, outline=outline, tags=(tag, "plus")
            )
            canvas.create_text(cx, cy - 1, text="+", fill=text, font=font, tags=(tag, "plus"))

    def _icon(self, action: str, on_accent: bool) -> ImageTk.PhotoImage:
        key = (action, on_accent)
        if key not in self._icons:
            glyph = {"rotl": "rotate_left", "rotr": "rotate_right", "del": "delete"}[action]
            color = style.themed(style.ON_ACCENT if on_accent else style.TEXT)
            size = round(self._scaled(ICON))
            image = render_glyph(GLYPHS[glyph], size, color) or Image.new("RGBA", (size * 3, size * 3))
            image = image.resize((size, size), Image.Resampling.LANCZOS)
            if action == "rotl":
                image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            self._icons[key] = ImageTk.PhotoImage(image, master=self.canvas)
        return self._icons[key]

    def _update_cards(self) -> None:
        """Colores de seleccion y de paso del cursor; muestra u oculta las acciones."""
        canvas = self.canvas
        accent = style.themed(style.accent_color())
        hover_fill = style.themed(style.ROW_BG)
        text, on_accent = style.themed(style.TEXT), style.themed(style.ON_ACCENT)
        card_bg, muted = style.themed(style.CARD_BG), style.themed(style.TEXT_MUTED)
        for page in range(self.page_count):
            selected = page in self.selected
            active = selected or page == self.hover
            fill = accent if selected else (hover_fill if page == self.hover else "")
            canvas.itemconfigure(f"bg{page}", fill=fill)
            canvas.itemconfigure(f"num{page}", fill=on_accent if selected else text)
            # Seleccionada: casilla blanca con la marca del color de acento (se ve sobre la tarjeta).
            canvas.itemconfigure(
                f"chkbox{page}", fill="white" if selected else card_bg, outline="white" if selected else muted
            )
            canvas.itemconfigure(f"tick{page}", state="normal" if selected else "hidden", fill=accent)
            for action in ("rotl", "rotr", "del"):
                canvas.itemconfigure(
                    f"{action}{page}", state="normal" if active else "hidden", image=self._icon(action, selected)
                )
        canvas.tag_raise("plus")

    def _draw_empty(self) -> None:
        canvas = self.canvas
        width, height = max(canvas.winfo_width(), 300), max(canvas.winfo_height(), 200)
        canvas.configure(scrollregion=(0, 0, width, height))
        muted = style.themed(style.TEXT_MUTED)
        inset = self._scaled(16)
        canvas.create_rectangle(inset, inset, width - inset, height - inset, outline=muted, dash=(6, 5))
        canvas.create_text(
            width / 2,
            height / 2 - self._scaled(10),
            text=tr("Abra o arrastre un PDF para organizar sus páginas"),
            fill=style.themed(style.TEXT),
            font=(style.FONT_FAMILY, round(self._scaled(13)), "bold"),
        )
        canvas.create_text(
            width / 2,
            height / 2 + self._scaled(16),
            text=tr("Arrastre las páginas para cambiar el orden; gírelas, elimínelas o inserte otras con +."),
            fill=muted,
            font=(style.FONT_FAMILY, round(self._scaled(10))),
        )

    # * Miniaturas (solo las visibles) --------------------------------------------------

    def _schedule_update(self) -> None:
        if self._update_job is None:
            self._update_job = self.after_idle(self._update_visible)

    def _update_visible(self) -> None:
        self._update_job = None
        if self.document is None or not self._cells:
            return
        m = self._metrics()
        top = self.canvas.canvasy(0) - m["card_h"]
        bottom = self.canvas.canvasy(0) + self.canvas.winfo_height() + m["card_h"]
        for page, (_x, y) in enumerate(self._cells):
            if not top <= y <= bottom:
                continue
            box = self._box(page, m)
            rect = self.document[page].rect
            scale = (box[2] - box[0]) / rect.width
            entry = self._images.get(page)
            if entry is None or entry[2] != scale_key(scale):
                self.scheduler.request(page, scale, self._place_image, priority=y)

    def _place_image(self, page: int, scale: float, photo: ImageTk.PhotoImage, _tile=None) -> None:
        if page >= len(self._cells):
            return
        m = self._metrics()
        box = self._box(page, m)
        old = self._images.pop(page, None)
        if old is not None:
            self.canvas.delete(old[0])
        item = self.canvas.create_image(box[0], box[1], anchor="nw", image=photo, tags=(f"card{page}", f"img{page}"))
        self.canvas.tag_raise(item, f"paper{page}")
        self._images[page] = (item, photo, scale_key(scale))
        self.canvas.tag_raise("action")
        self.canvas.tag_raise("chk")
        self.canvas.tag_raise("plus")

    def _scroll(self, rows: int) -> None:
        if rows:
            self.canvas.yview_scroll(rows, "units")
            self._schedule_update()

    def _yview(self, *args) -> None:
        self.canvas.yview(*args)
        self._schedule_update()

    # * Raton ----------------------------------------------------------------------------

    def _hit(self, event) -> tuple[str, int] | None:
        """Que hay bajo el raton: ``("card"|"chk"|"rotl"|"rotr"|"del"|"plus", indice)``."""
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        for item in reversed(self.canvas.find_overlapping(x, y, x, y)):
            if self.canvas.itemcget(item, "state") == "hidden":
                continue
            for tag in self.canvas.gettags(item):
                for kind in ("plus", "chk", "rotl", "rotr", "del", "card"):
                    if tag.startswith(kind) and tag[len(kind) :].isdigit():
                        return kind, int(tag[len(kind) :])
        return None

    def _on_press(self, event) -> None:
        self.canvas.focus_set()
        if self.document is None:
            if self.on_empty_click:
                self.on_empty_click()
            return
        hit = self._hit(event)
        self._press = (event.x, event.y, hit[1] if hit and hit[0] == "card" else None)
        self._dragging = False
        if hit is None:
            return
        kind, index = hit
        if kind == "plus":
            self.on_insert(index, event.x_root, event.y_root)
        elif kind == "chk":
            self._toggle(index)
        elif kind in ("rotl", "rotr", "del"):
            pages = self.selection() if index in self.selected else [index]
            if kind == "del":
                self.on_delete(pages)
            else:
                self.on_rotate(pages, -90 if kind == "rotl" else 90)
        elif kind == "card":
            if event.state & 0x0004:  # Ctrl: agrega o quita
                self._toggle(index)
            elif event.state & 0x0001 and self.anchor is not None:  # Mayus: rango
                low, high = sorted((self.anchor, index))
                self.set_selection(list(range(low, high + 1)))
            elif index not in self.selected:
                self.anchor = index
                self.set_selection([index])

    def _toggle(self, index: int) -> None:
        self.anchor = index
        pages = set(self.selected)
        pages.symmetric_difference_update({index})
        self.set_selection(sorted(pages))

    def _on_drag(self, event) -> None:
        if self._press is None:
            return
        start_x, start_y, page = self._press
        if page is None:
            return
        if not self._dragging and abs(event.x - start_x) + abs(event.y - start_y) < DRAG_THRESHOLD:
            return
        if not self._dragging:
            self._dragging = True
            if page not in self.selected:
                self.set_selection([page])
            self.canvas.configure(cursor="fleur")
        self._autoscroll(event)
        self._drop_index = self._index_at(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
        self._draw_drop_marker()

    def _on_release(self, event) -> None:
        press, dragging, drop = self._press, self._dragging, self._drop_index
        self._press, self._dragging, self._drop_index = None, False, None
        self.canvas.configure(cursor="")
        self.canvas.delete("drop")
        if dragging and drop is not None:
            self.on_move(self.selection(), drop)
        elif press is not None and press[2] is not None and not dragging and not (event.state & 0x0005):
            # Clic simple sobre una pagina ya seleccionada (entre varias): queda solo ella.
            hit = self._hit(event)
            if hit == ("card", press[2]) and len(self.selected) > 1:
                self.anchor = press[2]
                self.set_selection([press[2]])

    def _on_motion(self, event) -> None:
        hit = self._hit(event)
        page = hit[1] if hit and hit[0] in ("card", "chk", "rotl", "rotr", "del") else None
        self._set_hover(page)
        tips = {
            "plus": tr("Insertar páginas aquí"),
            "rotl": tr("Girar a la izquierda"),
            "rotr": tr("Girar a la derecha"),
            "del": tr("Eliminar"),
            "chk": tr("Seleccionar"),
        }
        hint = tips.get(hit[0], "") if hit else ""
        if hint != self.hint:
            self.hint = hint
            self.on_hint(hint)
        self.canvas.configure(cursor="hand2" if hit and hit[0] != "card" else "")

    def _set_hover(self, page: int | None) -> None:
        if page != self.hover:
            self.hover = page
            self._update_cards()

    def _index_at(self, x: float, y: float) -> int:
        """Posicion de insercion (0..page_count) mas cercana al punto."""
        if not self._cells:
            return 0
        m = self._metrics()
        best, best_distance = 0, float("inf")
        for page, (cx, cy) in enumerate(self._cells):
            if not cy - m["row_gap"] <= y <= cy + m["card_h"] + m["row_gap"]:
                continue
            for index, edge in ((page, cx), (page + 1, cx + m["card_w"])):
                distance = abs(x - edge)
                if distance < best_distance:
                    best, best_distance = index, distance
        if best_distance == float("inf"):  # debajo de la ultima fila
            return self.page_count if y > self._cells[-1][1] else 0
        return best

    def _draw_drop_marker(self) -> None:
        self.canvas.delete("drop")
        index = self._drop_index
        if index is None or not self._cells:
            return
        m = self._metrics()
        if index < len(self._cells):
            x, y = self._cells[index]
            x -= m["gap"] / 2
        else:
            x, y = self._cells[-1]
            x += m["card_w"] + m["gap"] / 2
        width = self._scaled(4)
        self.canvas.create_rectangle(
            x - width / 2,
            y,
            x + width / 2,
            y + m["card_h"],
            fill=style.themed(style.accent_color()),
            outline="",
            tags="drop",
        )

    def _autoscroll(self, event) -> None:
        margin = self._scaled(AUTOSCROLL_MARGIN)
        if event.y < margin:
            self._scroll(-1)
        elif event.y > self.canvas.winfo_height() - margin:
            self._scroll(1)
