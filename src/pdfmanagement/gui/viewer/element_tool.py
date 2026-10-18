"""
Herramienta "Seleccionar" del visor: elegir con el raton lo que hay en la
pagina (anotaciones, lineas de texto e imagenes).

Al pasar el cursor se marca lo que hay debajo; un clic lo selecciona. Las
anotaciones se mueven arrastrandolas; el doble clic edita el texto (de una
linea o de una nota) y Supr elimina lo seleccionado.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import pymupdf

from ...core.editing import AnnotationInfo
from ...core.editing.content import PageElement
from .. import style
from .page_view import PageHit, PageView, Tool

DRAG_THRESHOLD = 4
HOVER = ("#3B82F6", "#60A5FA")


@dataclass(frozen=True)
class Selection:
    """Lo seleccionado: una anotacion o un elemento del contenido de la pagina."""

    page: int
    annotation: AnnotationInfo | None = None
    element: PageElement | None = None

    @property
    def rect(self) -> pymupdf.Rect:
        if self.annotation is not None:
            return self.annotation.rect
        assert self.element is not None
        return self.element.rect


class ElementTool(Tool):
    cursor = "arrow"

    def __init__(
        self,
        *,
        elements_for: Callable[[int], list[PageElement]],
        hit_annotation: Callable[[PageHit], AnnotationInfo | None],
        on_select: Callable[[Selection | None], None],
        on_move: Callable[[AnnotationInfo, float, float], None],
        on_edit: Callable[[Selection], None],
    ) -> None:
        self.elements_for = elements_for
        self.hit_annotation = hit_annotation
        self.on_select = on_select
        self.on_move = on_move
        self.on_edit = on_edit
        self.hover: Selection | None = None
        self._grabbed: AnnotationInfo | None = None
        self._press_xy = (0, 0)
        self._offset: tuple[float, float] | None = None

    def find(self, hit: PageHit | None) -> Selection | None:
        """Lo que hay bajo el punto: primero las anotaciones (estan encima), luego el contenido."""
        if hit is None:
            return None
        annotation = self.hit_annotation(hit)
        if annotation is not None:
            return Selection(hit.page, annotation=annotation)
        point = pymupdf.Point(hit.x, hit.y)
        candidates = [
            element for element in self.elements_for(hit.page) if (element.rect + (-2, -2, 2, 2)).contains(point)
        ]
        if not candidates:
            return None
        # Si una linea esta sobre una imagen, la linea (la mas chica) es la que se quiere.
        element = min(candidates, key=lambda item: item.rect.width * item.rect.height)
        return Selection(hit.page, element=element)

    # * Eventos ---------------------------------------------------------------

    def motion(self, view: PageView, event, hit: PageHit | None) -> None:
        found = self.find(hit)
        if found != self.hover:
            self.hover = found
            view.canvas.configure(cursor="hand2" if found is not None else self.cursor)
            view.redraw_overlays()

    def press(self, view: PageView, event, hit: PageHit | None) -> None:
        self._press_xy = (event.x, event.y)
        self._offset = None
        found = self.find(hit)
        self._grabbed = found.annotation if found is not None else None
        self.on_select(found)

    def drag(self, view: PageView, event, hit: PageHit | None) -> None:
        grabbed = self._grabbed
        if grabbed is None or not grabbed.movable:
            return
        if abs(event.x - self._press_xy[0]) + abs(event.y - self._press_xy[1]) < DRAG_THRESHOLD:
            return
        self._offset = ((event.x - self._press_xy[0]) / view.scale, (event.y - self._press_xy[1]) / view.scale)
        view.canvas.configure(cursor="fleur")
        view.redraw_overlays()

    def release(self, view: PageView, event, hit: PageHit | None) -> None:
        grabbed, offset = self._grabbed, self._offset
        self._grabbed = self._offset = None
        view.canvas.configure(cursor=self.cursor)
        if grabbed is not None and offset is not None and (abs(offset[0]) > 0.5 or abs(offset[1]) > 0.5):
            self.on_move(grabbed, *offset)
        view.redraw_overlays()

    def double(self, view: PageView, event, hit: PageHit | None) -> None:
        found = self.find(hit)
        if found is not None:
            self.on_edit(found)

    def draw(self, view: PageView) -> None:
        hover = self.hover
        if hover is not None and hover.page in view.visible_pages():
            view.draw_rect(hover.page, hover.rect, pad=2, outline=style.themed(HOVER), width=1.5, dash=(4, 3))
        if self._grabbed is not None and self._offset is not None:
            dx, dy = self._offset
            view.draw_rect(
                self._grabbed.page,
                self._grabbed.rect + (dx, dy, dx, dy),
                pad=3,
                outline=style.themed(style.accent_color()),
                width=2,
                dash=(5, 3),
            )
