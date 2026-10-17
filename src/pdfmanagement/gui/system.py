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
