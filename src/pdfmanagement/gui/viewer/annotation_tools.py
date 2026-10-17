"""
Herramientas de anotacion del visor.

Solo capturan el gesto (arrastre, clic, trazo) y lo informan en coordenadas
de la pagina tal como se ve; quien las usa (``ViewerAnnotations``) crea la
anotacion en el documento. Mientras se arrastra se dibuja una vista previa con
la etiqueta "overlay", que el visor borra y redibuja.
"""

from __future__ import annotations

from collections.abc import Callable

import pymupdf

from ...core.editing import AnnotationInfo
from .. import style
from .page_view import PageHit, PageView, Tool
from .tools import TextSelectTool

Point = tuple[float, float]
DRAG_THRESHOLD = 4  # pixeles: menos es un clic


def tk_color(color: tuple[float, float, float]) -> str:
    red, green, blue = (round(max(0.0, min(1.0, value)) * 255) for value in color)
    return f"#{red:02x}{green:02x}{blue:02x}"


class MarkupTool(TextSelectTool):
    """Resaltar, subrayar o tachar: se arrastra sobre el texto como al seleccionarlo."""

    def __init__(self, kind: str, words_for, on_markup: Callable[[str, dict[int, list[pymupdf.Rect]]], None]) -> None:
        super().__init__(words_for)
        self.kind = kind
        self.on_markup = on_markup

    def release(self, view: PageView, event, hit: PageHit | None) -> None:
        lines = line_rects(self.selected_words())
        self.clear(view)
        if lines:
            self.on_markup(self.kind, lines)


def line_rects(selected: list[tuple[int, tuple]]) -> dict[int, list[pymupdf.Rect]]:
    """Une las palabras de cada linea en un rectangulo: la marca queda continua."""
    lines: dict[tuple[int, int, int], pymupdf.Rect] = {}
    for page, word in selected:
        key = (page, word[5], word[6])
        rect = pymupdf.Rect(word[:4])
        lines[key] = lines[key] | rect if key in lines else rect
    result: dict[int, list[pymupdf.Rect]] = {}
    for (page, _block, _line), rect in lines.items():
        result.setdefault(page, []).append(rect)
    return result


class DragTool(Tool):
    """
    Rectangulo, elipse, linea, flecha o cuadro de texto: se arrastra de una
    esquina a otra. Un clic sin arrastrar informa ``start == end``.
    """

    cursor = "crosshair"

    def __init__(
        self,
        kind: str,
        on_done: Callable[[str, int, Point, Point], None],
        color: Callable[[], tuple[float, float, float]],
        width: Callable[[], float],
    ) -> None:
        self.kind = kind
        self.on_done = on_done
        self.color = color
        self.width = width
        self._start: PageHit | None = None
        self._end: Point | None = None
        self._press_xy = (0, 0)

    def press(self, view: PageView, event, hit: PageHit | None) -> None:
        self._start = hit
        self._end = (hit.x, hit.y) if hit else None
        self._press_xy = (event.x, event.y)

    def drag(self, view: PageView, event, hit: PageHit | None) -> None:
        if self._start is None:
            return
        point = view.canvas_to_page(view.canvas.canvasx(event.x), view.canvas.canvasy(event.y), clamp=True)
        if point is not None and point.page == self._start.page:
            self._end = (point.x, point.y)
            view.redraw_overlays()

    def release(self, view: PageView, event, hit: PageHit | None) -> None:
        start, end = self._start, self._end
        self._start = self._end = None
        view.redraw_overlays()
        if start is None or end is None:
            return
        moved = abs(event.x - self._press_xy[0]) + abs(event.y - self._press_xy[1]) >= DRAG_THRESHOLD
        self.on_done(self.kind, start.page, (start.x, start.y), end if moved else (start.x, start.y))

    def draw(self, view: PageView) -> None:
        if self._start is None or self._end is None:
            return
        x0, y0 = view.page_to_canvas(self._start.page, self._start.x, self._start.y)
        x1, y1 = view.page_to_canvas(self._start.page, *self._end)
        color = tk_color(self.color())
        width = max(1.0, self.width() * view.scale)
        if self.kind == "redact":
            view.canvas.create_rectangle(x0, y0, x1, y1, fill="black", stipple="gray50", outline="", tags="overlay")
        elif self.kind == "image":
            view.canvas.create_rectangle(x0, y0, x1, y1, outline=color, width=1.5, dash=(6, 4), tags="overlay")
        elif self.kind in ("rect", "free_text"):
            dash = (4, 3) if self.kind == "free_text" else ()
            view.canvas.create_rectangle(x0, y0, x1, y1, outline=color, width=width, dash=dash, tags="overlay")
        elif self.kind == "ellipse":
            view.canvas.create_oval(x0, y0, x1, y1, outline=color, width=width, tags="overlay")
        else:
            arrow = "last" if self.kind == "arrow" else "none"
            view.canvas.create_line(  # type: ignore[call-overload]  # arrowshape admite tres numeros
                x0,
                y0,
                x1,
                y1,
                fill=color,
                width=width,
                arrow=arrow,
                arrowshape=(round(10 + width * 2), round(12 + width * 2), round(4 + width)),
                tags="overlay",
            )


class InkTool(Tool):
    """Dibujo a mano alzada."""

    cursor = "pencil"

    def __init__(
        self,
        on_done: Callable[[int, list[Point]], None],
        color: Callable[[], tuple[float, float, float]],
        width: Callable[[], float],
    ) -> None:
        self.on_done = on_done
        self.color = color
        self.width = width
        self._page: int | None = None
        self._points: list[Point] = []

    def press(self, view: PageView, event, hit: PageHit | None) -> None:
        self._page = hit.page if hit else None
        self._points = [(hit.x, hit.y)] if hit else []

    def drag(self, view: PageView, event, hit: PageHit | None) -> None:
        if self._page is None:
            return
        point = view.canvas_to_page(view.canvas.canvasx(event.x), view.canvas.canvasy(event.y), clamp=True)
        if point is None or point.page != self._page:
            return
        last = self._points[-1]
        if abs(point.x - last[0]) + abs(point.y - last[1]) >= 1.5:  # sin puntos redundantes
            self._points.append((point.x, point.y))
            if len(self._points) >= 2:
                (ax, ay), (bx, by) = self._points[-2], self._points[-1]
                x0, y0 = view.page_to_canvas(self._page, ax, ay)
                x1, y1 = view.page_to_canvas(self._page, bx, by)
                view.canvas.create_line(
                    x0,
                    y0,
                    x1,
                    y1,
                    fill=tk_color(self.color()),
                    capstyle="round",
                    width=max(1.0, self.width() * view.scale),
                    tags=("overlay", "ink"),
                )

    def release(self, view: PageView, event, hit: PageHit | None) -> None:
        page, points = self._page, self._points
        self._page, self._points = None, []
        view.canvas.delete("ink")
        if page is not None and len(points) >= 2:
            self.on_done(page, points)

    def draw(self, view: PageView) -> None:
        if self._page is None or len(self._points) < 2:
            return
        coords = [value for x, y in self._points for value in view.page_to_canvas(self._page, x, y)]
        view.canvas.create_line(
            *coords,
            fill=tk_color(self.color()),
            capstyle="round",
            joinstyle="round",
            width=max(1.0, self.width() * view.scale),
            tags=("overlay", "ink"),
        )


class NoteTool(Tool):
    """Clic donde va la nota."""

    cursor = "hand2"

    def __init__(self, on_done: Callable[[int, Point], None]) -> None:
        self.on_done = on_done

    def press(self, view: PageView, event, hit: PageHit | None) -> None:
        if hit is not None:
            self.on_done(hit.page, (hit.x, hit.y))


class SelectTool(TextSelectTool):
    """
    Herramienta "Texto": selecciona texto y, si el clic cae sobre una
    anotacion, la selecciona. Arrastrar una anotacion seleccionada la mueve;
    doble clic edita el texto de notas y cuadros de texto. Sobre una marca de
    texto (resaltado, subrayado...) arrastrar sigue seleccionando el texto.
    """

    def __init__(
        self,
        words_for,
        on_change,
        *,
        hit_annotation: Callable[[PageHit], AnnotationInfo | None],
        on_select: Callable[[AnnotationInfo | None], None],
        on_move: Callable[[AnnotationInfo, float, float], None],
        on_edit: Callable[[AnnotationInfo], None],
    ) -> None:
        super().__init__(words_for, on_change)
        self.hit_annotation = hit_annotation
        self.on_select = on_select
        self.on_move = on_move
        self.on_edit = on_edit
        self._grabbed: AnnotationInfo | None = None  # anotacion bajo el clic
        self._grab_hit: PageHit | None = None
        self._press_xy = (0, 0)
        self._offset: Point | None = None  # desplazamiento de la vista previa
        self._texting = False

    def press(self, view: PageView, event, hit: PageHit | None) -> None:
        self._press_xy = (event.x, event.y)
        self._offset = None
        self._texting = False
        annotation = self.hit_annotation(hit) if hit else None
        self._grabbed, self._grab_hit = annotation, hit
        if annotation is None:
            self.on_select(None)
            super().press(view, event, hit)
            return
        self.clear(view)
        self.on_select(annotation)

    def drag(self, view: PageView, event, hit: PageHit | None) -> None:
        if self._grabbed is None:
            super().drag(view, event, hit)
            return
        if self._texting:
            super().drag(view, event, hit)
            return
        if abs(event.x - self._press_xy[0]) + abs(event.y - self._press_xy[1]) < DRAG_THRESHOLD:
            return
        if not getattr(self._grabbed, "movable", False):
            # Marca de texto: el arrastre selecciona el texto que hay debajo.
            self._texting = True
            self.on_select(None)
            super().press(view, event, self._grab_hit)
            super().drag(view, event, hit)
            return
        self._offset = ((event.x - self._press_xy[0]) / view.scale, (event.y - self._press_xy[1]) / view.scale)
        view.canvas.configure(cursor="fleur")
        view.redraw_overlays()

    def release(self, view: PageView, event, hit: PageHit | None) -> None:
        grabbed, offset = self._grabbed, self._offset
        self._grabbed = self._offset = None
        view.canvas.configure(cursor=self.cursor)
        if grabbed is None or self._texting:
            self._texting = False
            super().release(view, event, hit)
            return
        if offset is not None and (abs(offset[0]) > 0.5 or abs(offset[1]) > 0.5):
            self.on_move(grabbed, *offset)
        view.redraw_overlays()

    def double(self, view: PageView, event, hit: PageHit | None) -> None:
        annotation = self.hit_annotation(hit) if hit else None
        if annotation is not None and getattr(annotation, "has_text", False):
            self.on_edit(annotation)

    def draw(self, view: PageView) -> None:
        if self._grabbed is None or self._offset is None:
            return
        rect = self._grabbed.rect + (self._offset[0], self._offset[1], self._offset[0], self._offset[1])
        view.draw_rect(
            self._grabbed.page,
            rect,
            pad=3,
            outline=style.themed(style.accent_color()),
            width=2,
            dash=(5, 3),
        )
