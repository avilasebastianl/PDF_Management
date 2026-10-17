"""
Documento abierto para ver y editar: sesion, historial de cambios y busqueda.

La interfaz trabaja siempre a traves de ``DocumentSession`` para que todas las
herramientas (visor, firmas, edicion) compartan el mismo estado.
"""

from .annotations import AnnotationInfo, AnnotationStyle
from .history import History
from .search import SearchHit, SearchOptions, iter_search, search_page
from .session import DocumentProperties, DocumentSession

__all__ = [
    "AnnotationInfo",
    "AnnotationStyle",
    "DocumentProperties",
    "DocumentSession",
    "History",
    "SearchHit",
    "SearchOptions",
    "iter_search",
    "search_page",
]
