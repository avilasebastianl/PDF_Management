"""
Visor de PDF reutilizable: lo usan la seccion Visor y Firmar.

- ``PageView``: lienzo con las paginas (continuo o pagina unica, virtualizado).
- ``RenderScheduler``: dibujo cooperativo en el hilo de la interfaz con cache.
- ``ViewerToolbar``: navegacion y zoom.
- ``ThumbnailStrip``: miniaturas.
- ``Tool``, ``TextSelectTool``, ``HandTool``: herramientas sobre las paginas.
"""

from .page_view import BASE_SCALE, FIT_PAGE, FIT_WIDTH, PageHit, PageView, Tool
from .render import RenderScheduler
from .thumbnails import ThumbnailStrip
from .toolbar import ViewerToolbar
from .tools import HandTool, TextSelectTool

__all__ = [
    "BASE_SCALE",
    "FIT_PAGE",
    "FIT_WIDTH",
    "HandTool",
    "PageHit",
    "PageView",
    "RenderScheduler",
    "TextSelectTool",
    "ThumbnailStrip",
    "Tool",
    "ViewerToolbar",
]
