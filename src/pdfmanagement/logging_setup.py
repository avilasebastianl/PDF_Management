"""
Configuracion central del registro (logging).

- ``log/app.log``: actividad general (INFO o DEBUG con ``--debug``).
- ``log/error.log``: solo errores, con traza completa.
- Consola: solo si existe (``pythonw`` no tiene consola).

Los archivos rotan al llegar a 1 MB y se conservan 3 copias.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import paths

_FILE_FORMAT = logging.Formatter("[%(asctime)s] %(levelname)-8s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
_CONSOLE_FORMAT = logging.Formatter("[%(levelname)s] %(message)s")


def configure_logging(log_dir: Path | None = None, debug: bool = False) -> None:
    """Configura el logger ``pdfmanagement`` y captura excepciones no controladas."""
    log_dir = log_dir or paths.LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("pdfmanagement")
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.handlers.clear()

    app_handler = RotatingFileHandler(log_dir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    app_handler.setFormatter(_FILE_FORMAT)
    logger.addHandler(app_handler)

    error_handler = RotatingFileHandler(log_dir / "error.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(_FILE_FORMAT)
    logger.addHandler(error_handler)

    if sys.stderr is not None:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG if debug else logging.WARNING)
        console_handler.setFormatter(_CONSOLE_FORMAT)
        logger.addHandler(console_handler)

    def log_uncaught(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical("Excepcion no controlada", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = log_uncaught
