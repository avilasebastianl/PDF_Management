"""
Archivos abiertos recientemente en el visor (``config/recent.json``).
"""

import json
import logging
from pathlib import Path

from . import paths

logger = logging.getLogger(__name__)

MAX_RECENT = 10


def _recent_file() -> Path:
    return paths.CONFIG_DIR / "recent.json"


def load_recent() -> list[Path]:
    """Recientes que todavia existen, del mas nuevo al mas viejo."""
    try:
        entries = json.loads(_recent_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [Path(entry) for entry in entries if isinstance(entry, str) and Path(entry).exists()][:MAX_RECENT]


def add_recent(file: Path) -> list[Path]:
    """Agrega (o sube al principio) un archivo y devuelve la lista actualizada."""
    file = Path(file).resolve()
    entries = [file, *[entry for entry in load_recent() if entry != file]][:MAX_RECENT]
    try:
        _recent_file().parent.mkdir(parents=True, exist_ok=True)
        _recent_file().write_text(json.dumps([str(entry) for entry in entries], indent=2), encoding="utf-8")
    except OSError as error:
        logger.warning("No se pudo guardar la lista de recientes: %s", error)
    return entries


def clear_recent() -> None:
    _recent_file().unlink(missing_ok=True)
