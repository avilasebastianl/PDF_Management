"""
Historial de cambios (deshacer / rehacer) de un documento abierto.

Usa el *journal* nativo de MuPDF: cada operacion se agrupa con una etiqueta
legible ("Rotar pagina 3") y se puede deshacer o rehacer sin limite.

Reglas verificadas con PyMuPDF 1.28:

- Funciona con anotaciones, operaciones de pagina y texto insertado (si la
  fuente se carga antes de iniciar la operacion).
- Guardar con compactacion (``garbage``) sobre el documento vivo rompe el
  historial; por eso ``DocumentSession.save_as`` guarda desde una copia.
"""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pymupdf

logger = logging.getLogger(__name__)


class History:
    """Pilas de deshacer / rehacer sobre el journal de un ``pymupdf.Document``."""

    def __init__(self, document: pymupdf.Document, on_change: Callable[[], None] | None = None) -> None:
        self._document = document
        self._undo: list[str] = []
        self._redo: list[str] = []
        self._saved_depth = 0  # profundidad de la pila al ultimo guardado
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
    def undo_label(self) -> str | None:
        return self._undo[-1] if self._undo else None

    @property
    def redo_label(self) -> str | None:
        return self._redo[-1] if self._redo else None

    @property
    def modified(self) -> bool:
        """Hay cambios respecto del ultimo guardado (o de la apertura)."""
        return len(self._undo) != self._saved_depth

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
        self._undo.append(label)
        self._redo.clear()
        logger.debug("Operacion registrada: %s (deshacer: %d)", label, len(self._undo))
        self._changed()

    def undo(self) -> str | None:
        """Deshace la ultima operacion; devuelve su etiqueta."""
        if not self._undo:
            return None
        self._document.journal_undo()
        label = self._undo.pop()
        self._redo.append(label)
        self._changed()
        return label

    def redo(self) -> str | None:
        """Rehace la ultima operacion deshecha; devuelve su etiqueta."""
        if not self._redo:
            return None
        self._document.journal_redo()
        label = self._redo.pop()
        self._undo.append(label)
        self._changed()
        return label

    def mark_saved(self) -> None:
        """El estado actual queda como "sin cambios" (tras guardar)."""
        self._saved_depth = len(self._undo)
        self._changed()

    def _changed(self) -> None:
        if self._on_change:
            self._on_change()
