"""
Operaciones de pagina compatibles con el historial (journal) de MuPDF.

``Document.insert_pdf`` y ``Document.new_page`` de PyMuPDF 1.28 no se pueden
usar con el journal activo: comprueban el estado con ``pdf_undoredo_step``,
que MuPDF rechaza dentro de una operacion ("Can't undo/redo during an
operation"). Por eso insertar paginas usa directamente las primitivas de
MuPDF (``pdf_graft_mapped_page``, ``pdf_add_page``, en ``engine.py``), que si
quedan registradas y se pueden deshacer. Rotar, eliminar y reordenar usan la
API normal.

Todas las funciones reciben indices desde 0 y deben llamarse dentro de
``History.operation``.
"""

from collections.abc import Iterable, Sequence

import pymupdf

from . import engine


def rotate_pages(document: pymupdf.Document, pages: Iterable[int], angle: int) -> None:
    """Gira las paginas ``angle`` grados (multiplo de 90; positivo = horario)."""
    if angle % 90 or angle % 360 == 0:
        raise ValueError(f"Angulo no valido: {angle}")
    for index in pages:
        page = document[index]
        page.set_rotation((page.rotation + angle) % 360)


def delete_pages(document: pymupdf.Document, pages: Iterable[int]) -> None:
    document.delete_pages(sorted(set(pages)))


def move_pages(document: pymupdf.Document, pages: Iterable[int], target: int) -> list[int]:
    """
    Mueve ``pages`` (en su orden actual) para que queden antes de la pagina
    que hoy esta en ``target`` (``page_count`` = al final). Devuelve los nuevos
    indices de las paginas movidas.
    """
    moving = sorted(set(pages))
    count = document.page_count
    rest = [index for index in range(count) if index not in moving]
    position = sum(1 for index in rest if index < target)
    order = rest[:position] + moving + rest[position:]
    if order != list(range(count)):
        document.select(order)
    return list(range(position, position + len(moving)))


def insert_document(
    document: pymupdf.Document, source: pymupdf.Document, at: int, pages: Sequence[int] | None = None
) -> int:
    """
    Inserta las paginas ``pages`` de ``source`` (todas si es ``None``) antes de
    ``at``. Copia contenido, recursos, rotacion y anotaciones; los enlaces a
    otras paginas del documento de origen se descartan (apuntarian a paginas
    que no existen aqui). ``source`` se modifica: debe ser una copia propia.
    Devuelve la cantidad de paginas insertadas.
    """
    selected = list(range(source.page_count)) if pages is None else list(pages)
    engine.graft_pages(document, source, at, selected)
    return len(selected)


def insert_blank_page(document: pymupdf.Document, at: int, width: float, height: float) -> None:
    """Inserta una pagina en blanco de ``width`` x ``height`` puntos antes de ``at``."""
    engine.add_blank_page(document, at, width, height)
