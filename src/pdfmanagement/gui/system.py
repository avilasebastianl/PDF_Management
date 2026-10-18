"""
Integracion con el sistema operativo (abrir archivos y carpetas).
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def open_path(path: Path) -> None:
    """Abre un archivo o carpeta con la aplicacion predeterminada."""
    if not path.exists():
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", str(path)])
    except OSError as error:
        logger.error("No se pudo abrir %s: %s", path, error)


def reveal_in_folder(path: Path) -> None:
    """Abre la carpeta contenedora con el archivo seleccionado."""
    if not path.exists():
        return
    if sys.platform.startswith("win"):
        subprocess.Popen(f'explorer /select,"{path}"')
    else:
        open_path(path.parent)


def clear_topmost(window) -> None:
    """
    Quita el "siempre encima" de una ventana (solo Windows). Tk lo activa al
    pasar a pantalla completa: las demas aplicaciones quedaban detras (Alt+Tab
    no las traia al frente) y las listas desplegables se abrian debajo.
    """
    if not sys.platform.startswith("win"):
        return
    import ctypes
    from ctypes import wintypes

    set_window_pos = ctypes.windll.user32.SetWindowPos
    # Tipos explicitos: HWND_NOTOPMOST es (HWND)-2 y sin esto ctypes lo pasa truncado a 32 bits.
    set_window_pos.argtypes = [wintypes.HWND, wintypes.HWND] + [ctypes.c_int] * 4 + [wintypes.UINT]
    hwnd = int(window.wm_frame(), 16)  # la ventana de nivel superior (Tk la recrea al pasar a pantalla completa)
    flags = 0x0001 | 0x0002 | 0x0010  # SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE
    set_window_pos(hwnd, wintypes.HWND(-2), 0, 0, 0, 0, flags)
