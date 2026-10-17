"""
Registro de eventos de la interfaz: que hizo el usuario, en que seccion y con
que resultado. Facilita reconstruir una sesion al depurar.

Niveles:

- INFO (siempre): navegacion, cambios de ajustes, archivos agregados o
  quitados, firmas, operaciones con sus parametros y su resultado.
- DEBUG (modo detallado): zoom, paginas del visor, posicion y tamano de la
  firma, apertura de desplegables, tiempos internos.

Formato: ``[Seccion] mensaje  | clave=valor, ...``. Los valores cuya clave
parece una contrasena se ocultan siempre.
"""

import logging
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

logger = logging.getLogger("pdfmanagement.gui.events")

_SENSITIVE_KEYS = ("password", "contrasena", "clave", "secret")
_MAX_LISTED = 5


def log_event(area: str, message: str, *args, level: int = logging.INFO, **details) -> None:
    """Registra un evento de la seccion ``area`` (argumentos estilo ``%s``)."""
    if not logger.isEnabledFor(level):
        return
    text = f"[{area}] {message % args if args else message}"
    if details:
        text += "  | " + ", ".join(f"{key}={_format_value(key, value)}" for key, value in details.items())
    logger.log(level, one_line(text))


def one_line(text: object) -> str:
    """Una sola linea por evento: los saltos de linea se reemplazan por " / "."""
    return " / ".join(part.strip() for part in str(text).splitlines() if part.strip())


def debug_event(area: str, message: str, *args, **details) -> None:
    """Evento visible solo en modo detallado."""
    log_event(area, message, *args, level=logging.DEBUG, **details)


def area_of(widget) -> str:
    """Seccion (pagina) que contiene al widget, segun su atributo ``log_area``."""
    while widget is not None:
        area = getattr(widget, "log_area", None)
        if area:
            return area
        widget = getattr(widget, "master", None)
    return "General"


def describe_files(files: Iterable[Path | str], limit: int = _MAX_LISTED) -> str:
    """``a.pdf, b.pdf, c.pdf (+4 mas)`` para listas largas."""
    names = [Path(file).name for file in files]
    listed = ", ".join(names[:limit])
    return f"{listed} (+{len(names) - limit} mas)" if len(names) > limit else listed


@contextmanager
def timed(area: str, message: str, *args, level: int = logging.DEBUG) -> Iterator[None]:
    """Registra cuanto tardo un bloque: ``[Area] mensaje (123 ms)``."""
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed = (time.perf_counter() - started) * 1000
        log_event(area, f"{message % args if args else message} ({elapsed:.0f} ms)", level=level)


def _format_value(key: str, value: object) -> str:
    if any(fragment in key.lower() for fragment in _SENSITIVE_KEYS):
        return "***" if value else "(vacia)"
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)
