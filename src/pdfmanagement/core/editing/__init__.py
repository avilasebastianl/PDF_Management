"""
Documento abierto para ver y editar: sesion, historial de cambios y busqueda.

La interfaz trabaja siempre a traves de ``DocumentSession`` para que todas las
herramientas (visor, firmas, edicion) compartan el mismo estado.
"""

from . import engine
from .annotations import AnnotationInfo, AnnotationStyle
from .changes import CONTENT, SAVED, STRUCTURE, DocumentChange
from .history import History
from .search import SearchHit, SearchOptions, iter_search, search_page
from .session import DocumentProperties, DocumentSession

__all__ = [
    "CONTENT",
    "SAVED",
    "STRUCTURE",
    "AnnotationInfo",
    "AnnotationStyle",
    "DocumentChange",
    "DocumentProperties",
    "DocumentSession",
    "History",
    "SearchHit",
    "SearchOptions",
    "iter_search",
    "search_page",
]

engine.check_version()
