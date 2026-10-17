"""
Extraccion de texto en coordenadas de la pagina **tal como se ve**.

``Page.get_text`` y ``Page.search_for`` de PyMuPDF ponen la rotacion de la
pagina a 0 mientras extraen y la restauran despues. Eso tiene dos efectos:

- Con el historial (journal) activo, cambiar la rotacion fuera de una
  operacion lanza ``Can't alter an object other than in an operation``.
- Las coordenadas salen sin rotar, distintas de las que usa el visor.

Aqui el texto se extrae sin tocar la pagina: las coordenadas ya son las
visibles (verificado en 0/90/180/270 contra ``rotation_matrix``) y el
documento no se modifica.
"""

import pymupdf

WORD_FLAGS = pymupdf.TEXTFLAGS_WORDS
SEARCH_FLAGS = pymupdf.TEXTFLAGS_SEARCH


def visible_textpage(page: pymupdf.Page, flags: int = WORD_FLAGS) -> pymupdf.TextPage:
    """``TextPage`` de la pagina visible, sin modificar el documento."""
    # API interna de PyMuPDF (la misma que usa get_textpage, sin el cambio de
    # rotacion); tests/test_editing.py comprueba que siga existiendo.
    textpage = pymupdf.TextPage(page._get_textpage(None, flags=flags, matrix=pymupdf.Matrix(1, 1)))  # noqa: SLF001
    textpage.parent = page
    return textpage


def page_words(page: pymupdf.Page, *, sort: bool = False) -> list[tuple]:
    """
    Palabras ``(x0, y0, x1, y1, texto, bloque, linea, palabra)`` en
    coordenadas visibles; ``sort`` las ordena por linea y luego por x.
    """
    words = visible_textpage(page, WORD_FLAGS).extractWORDS()
    if sort:
        words.sort(key=lambda word: (word[3], word[0]))
    return words


def page_search(page: pymupdf.Page, query: str) -> list[pymupdf.Rect]:
    """Rectangulos (visibles) de ``query`` sin distinguir mayusculas."""
    return [pymupdf.Rect(rect) for rect in visible_textpage(page, SEARCH_FLAGS).search(query, quads=False)]
