"""
Herramientas basicas del visor: seleccionar texto y mano (desplazar).
"""

from __future__ import annotations

from collections.abc import Callable

import pymupdf

from .page_view import PageHit, PageView, Tool

Word = tuple  # (x0, y0, x1, y1, texto, bloque, linea, palabra)
AUTOSCROLL_MARGIN = 24


class HandTool(Tool):
    """Arrastrar para desplazar el documento."""

    cursor = "fleur"

    def press(self, view: PageView, event, hit: PageHit | None) -> None:
        view.canvas.scan_mark(event.x, event.y)

    def drag(self, view: PageView, event, hit: PageHit | None) -> None:
        view.canvas.scan_dragto(event.x, event.y, gain=1)
        view._schedule_update()  # noqa: SLF001 - el visor debe enterarse del desplazamiento


class TextSelectTool(Tool):
    """
    Seleccion de texto por palabras, en orden de lectura y a traves de varias
    paginas. ``words_for(pagina)`` devuelve las palabras ordenadas.
    """

    cursor = "xterm"

    def __init__(self, words_for: Callable[[int], list[Word]], on_change: Callable[[int], None] | None = None) -> None:
        self.words_for = words_for
        self.on_change = on_change
        self._anchor: tuple[int, int] | None = None
        self._focus: tuple[int, int] | None = None

    # * Eventos -------------------------------------------------------------

    def press(self, view: PageView, event, hit: PageHit | None) -> None:
        self._anchor = self._word_at(hit) if hit else None
        self._focus = self._anchor
        self._apply(view)

    def drag(self, view: PageView, event, hit: PageHit | None) -> None:
        if self._anchor is None or hit is None:
            return
        self._autoscroll(view, event)
        position = self._word_at(hit)
        if position is not None and position != self._focus:
            self._focus = position
            self._apply(view)

    def release(self, view: PageView, event, hit: PageHit | None) -> None:
        if self._anchor is not None and self._anchor == self._focus and not self._clicked_inside(hit):
            self.clear(view)

    # * Seleccion -----------------------------------------------------------

    def selected_words(self) -> list[tuple[int, Word]]:
        if self._anchor is None or self._focus is None:
            return []
        start, end = sorted((self._anchor, self._focus))
        selected: list[tuple[int, Word]] = []
        for page in range(start[0], end[0] + 1):
            words = self.words_for(page)
            first = start[1] if page == start[0] else 0
            last = end[1] if page == end[0] else len(words) - 1
            selected.extend((page, word) for word in words[first : last + 1])
        return selected

    def selected_text(self) -> str:
        """Texto seleccionado con saltos de linea donde los hay en el documento."""
        lines: list[str] = []
        previous: tuple | None = None
        for page, word in self.selected_words():
            key = (page, word[5], word[6])
            if previous is not None and key != previous:
                lines.append("\n")
            elif previous is not None:
                lines.append(" ")
            lines.append(word[4])
            previous = key
        return "".join(lines)

    def select_all(self, view: PageView, page: int) -> None:
        words = self.words_for(page)
        if words:
            self._anchor, self._focus = (page, 0), (page, len(words) - 1)
            self._apply(view)

    def clear(self, view: PageView) -> None:
        self._anchor = self._focus = None
        self._apply(view)

    def _apply(self, view: PageView) -> None:
        rects: dict[int, list[pymupdf.Rect]] = {}
        for page, word in self.selected_words():
            rects.setdefault(page, []).append(pymupdf.Rect(word[:4]))
        view.set_selection(rects)
        if self.on_change:
            self.on_change(len(self.selected_words()))

    # * Utilidades ----------------------------------------------------------

    def _word_at(self, hit: PageHit) -> tuple[int, int] | None:
        """Palabra bajo el punto o la mas cercana (priorizando la misma linea)."""
        words = self.words_for(hit.page)
        if not words:
            return None
        best, best_distance = 0, float("inf")
        for index, (x0, y0, x1, y1, *_rest) in enumerate(words):
            dx = 0.0 if x0 <= hit.x <= x1 else min(abs(hit.x - x0), abs(hit.x - x1))
            dy = 0.0 if y0 <= hit.y <= y1 else min(abs(hit.y - y0), abs(hit.y - y1))
            distance = dx + dy * 4
            if distance < best_distance:
                best, best_distance = index, distance
                if distance == 0:
                    break
        return hit.page, best

    def _clicked_inside(self, hit: PageHit | None) -> bool:
        if hit is None or self._anchor is None:
            return False
        x0, y0, x1, y1, *_ = self.words_for(self._anchor[0])[self._anchor[1]]
        return hit.page == self._anchor[0] and x0 <= hit.x <= x1 and y0 <= hit.y <= y1

    @staticmethod
    def _autoscroll(view: PageView, event) -> None:
        height = view.canvas.winfo_height()
        if event.y < AUTOSCROLL_MARGIN:
            view._scroll_units(-1)  # noqa: SLF001
        elif event.y > height - AUTOSCROLL_MARGIN:
            view._scroll_units(1)  # noqa: SLF001
