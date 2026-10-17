"""
Historial de cambios (deshacer / rehacer) de un documento abierto.

Usa el *journal* nativo de MuPDF: cada operacion se agrupa con una etiqueta
legible ("Rotar pagina 3") y se puede deshacer o rehacer sin limite.

Reglas verificadas con PyMuPDF 1.28:

- Funciona con anotaciones, operaciones de pagina y texto insertado (si la
  fuente se carga antes de iniciar la operacion).
- Guardar con compactacion (``garbage``) sobre el documento vivo rompe el
  historial; por eso ``DocumentSession.save_as`` guarda desde una copia.
- ``insert_pdf``, ``new_page``, ``show_pdf_page`` e ``insert_font`` fallan
  dentro de una operacion; ver ``pages.py`` para insertar paginas.
- ``Page.get_text`` cambia la rotacion de la pagina mientras extrae y eso
  falla con el journal activo; ver ``text.py``.
"""

import itertools
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pymupdf

logger = logging.getLogger(__name__)


class History:
    """Pilas de deshacer / rehacer sobre el journal de un ``pymupdf.Document``."""

    def __init__(self, document: pymupdf.Document, on_change: Callable[[], None] | None = None) -> None:
        self._document = document
        # Cada paso es (id, etiqueta); el id identifica el estado al que lleva.
        self._undo: list[tuple[int, str]] = []
        self._redo: list[tuple[int, str]] = []
        self._ids = itertools.count(1)
        self._saved_state: int | None = 0  # 0 = como se abrio; None = estado guardado ya inalcanzable
        self._on_change = on_change
        document.journal_enable()

    # * Consultas -----------------------------------------------------------

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_depth(self) -> int:
        """Pasos que se pueden deshacer (sirve para saber si una accion cambio algo)."""
        return len(self._undo)

    @property
    def undo_label(self) -> str | None:
        return self._undo[-1][1] if self._undo else None

    @property
    def redo_label(self) -> str | None:
        return self._redo[-1][1] if self._redo else None

    @property
    def modified(self) -> bool:
        """
        El documento difiere del ultimo guardado (o de la apertura). Deshacer
        hasta el estado guardado vuelve a "sin cambios"; si ese estado se
        pierde (se deshizo y se hizo otra cosa) queda modificado hasta guardar.
        """
        return self._state != self._saved_state

    @property
    def _state(self) -> int:
        return self._undo[-1][0] if self._undo else 0

    # * Operaciones ---------------------------------------------------------

    @contextmanager
    def operation(self, label: str) -> Iterator[None]:
        """
        Agrupa los cambios del bloque en un solo paso deshacible. Si el bloque
        falla, se deshace lo que alcanzo a modificar.
        """
        self._document.journal_start_op(label)
        try:
            yield
        except BaseException:
            self._document.journal_stop_op()
            self._document.journal_undo()
            raise
        self._document.journal_stop_op()
        if any(state == self._saved_state for state, _label in self._redo):
            self._saved_state = None
        self._undo.append((next(self._ids), label))
        self._redo.clear()
        logger.debug("Operacion registrada: %s (deshacer: %d)", label, len(self._undo))
        self._changed()

    def undo(self) -> str | None:
        """Deshace la ultima operacion; devuelve su etiqueta."""
        if not self._undo:
            return None
        self._document.journal_undo()
        step = self._undo.pop()
        self._redo.append(step)
        self._changed()
        return step[1]

    def redo(self) -> str | None:
        """Rehace la ultima operacion deshecha; devuelve su etiqueta."""
        if not self._redo:
            return None
        self._document.journal_redo()
        step = self._redo.pop()
        self._undo.append(step)
        self._changed()
        return step[1]

    def mark_saved(self) -> None:
        """El estado actual queda como "sin cambios" (tras guardar)."""
        self._saved_state = self._state
        self._changed()

    def _changed(self) -> None:
        # Las paginas cambian de lugar o desaparecen: los objetos Page en cache
        # de PyMuPDF quedarian apuntando a otra pagina.
        self._document._reset_page_refs()  # noqa: SLF001
        if self._on_change:
            self._on_change()
