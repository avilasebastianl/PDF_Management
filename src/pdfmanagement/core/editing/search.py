"""
Busqueda de texto en un documento.

``iter_search`` produce los resultados pagina por pagina para que la interfaz
pueda buscar por tramos (sin bloquearse en PDFs grandes) y mostrar resultados
a medida que aparecen.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass

import pymupdf


@dataclass(frozen=True)
class SearchHit:
    """Una coincidencia: pagina (desde 0), rectangulos que ocupa y contexto."""

    page: int
    rects: tuple[pymupdf.Rect, ...]
    context: str


@dataclass(frozen=True)
class SearchOptions:
    match_case: bool = False
    whole_words: bool = False


def iter_search(document: pymupdf.Document, query: str, options: SearchOptions = SearchOptions(),
                start_page: int = 0) -> Iterator[tuple[int, list[SearchHit]]]:
    """
    Recorre las paginas desde ``start_page`` (dando la vuelta al final) y
    produce ``(pagina, coincidencias)`` por cada una.
    """
    query = " ".join(query.split())
    if not query:
        return
    count = document.page_count
    for offset in range(count):
        index = (start_page + offset) % count
        yield index, search_page(document[index], index, query, options)


def search_page(page: pymupdf.Page, index: int, query: str, options: SearchOptions) -> list[SearchHit]:
    """Coincidencias de ``query`` en una pagina."""
    if not options.match_case and not options.whole_words:
        # Busqueda nativa de MuPDF: rapida, admite frases y no distingue mayusculas.
        rects = page.search_for(query)
        # Orden nativo de MuPDF: para el contexto basta y ordenar costaba ~20 ms por pagina.
        words = page.get_text("words") if rects else []
        return [SearchHit(index, (rect,), _context_for(words, rect)) for rect in rects]
    return _search_words(page, index, query, options)


def _search_words(page: pymupdf.Page, index: int, query: str, options: SearchOptions) -> list[SearchHit]:
    """Busqueda por palabras (distinguir mayusculas y/o palabra completa, admite frases)."""
    words = page.get_text("words", sort=True)
    terms = query.split()
    if not terms:
        return []
    flags = 0 if options.match_case else re.IGNORECASE
    patterns = [
        re.compile(rf"(?<!\w){re.escape(term)}(?!\w)" if options.whole_words else re.escape(term), flags)
        for term in terms
    ]
    hits: list[SearchHit] = []
    for start in range(len(words) - len(terms) + 1):
        candidate = words[start:start + len(terms)]
        if all(pattern.search(word[4]) for pattern, word in zip(patterns, candidate)):
            if len(terms) > 1 and not all(_exact_inner(word[4], term, options) for word, term in zip(candidate[1:-1], terms[1:-1])):
                continue
            rects = tuple(pymupdf.Rect(word[:4]) for word in candidate)
            hits.append(SearchHit(index, rects, _context_for(words, rects[0], start)))
    return hits


def _exact_inner(word: str, term: str, options: SearchOptions) -> bool:
    """En frases, las palabras intermedias deben coincidir completas."""
    return word == term if options.match_case else word.lower() == term.lower()


def _context_for(words: list[tuple], rect: pymupdf.Rect, index: int | None = None, span: int = 5) -> str:
    """Texto alrededor de la coincidencia para la lista de resultados."""
    if index is None:
        # Comparaciones con numeros simples: crear un pymupdf.Rect por palabra es
        # ~100 veces mas lento y dominaba el tiempo de busqueda.
        center_x, center_y = (rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2
        index = next(
            (position for position, (x0, y0, x1, y1, *_rest) in enumerate(words)
             if x0 <= center_x <= x1 and y0 <= center_y <= y1),
            None,
        )
        if index is None:
            return ""
    start = max(index - span, 0)
    snippet = " ".join(word[4] for word in words[start:index + span + 1])
    return ("..." if start else "") + snippet + ("..." if index + span + 1 < len(words) else "")
