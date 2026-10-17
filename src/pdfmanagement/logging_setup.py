"""
Configuracion central del registro (logging).

- ``log/app.log``: actividad general. Nivel INFO (acciones del usuario,
  operaciones y sus resultados) o DEBUG en modo detallado.
- ``log/error.log``: solo errores, con traza completa.
- Consola: solo si existe (``pythonw`` no tiene consola).

El modo detallado se activa con ``--debug``, con la variable de entorno
``PDFMANAGEMENT_DEBUG=1`` o desde Ajustes (sin reiniciar, ver ``set_debug``).

Formato de cada linea::

    [2026-10-17 10:15:02.481] INFO    MainThread    gui.events: [Unir] Agregados 3 archivos: a.pdf, b.pdf, c.pdf

Los archivos rotan al llegar a 1 MB y se conservan 3 copias.
"""

import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import paths

ROOT_LOGGER = "pdfmanagement"
DEBUG_ENV_VAR = "PDFMANAGEMENT_DEBUG"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class _Formatter(logging.Formatter):
    """Agrega milisegundos, el hilo y un nombre de logger corto (sin ``pdfmanagement.``)."""

    def format(self, record: logging.LogRecord) -> str:
        record.short_name = record.name.removeprefix(f"{ROOT_LOGGER}.")
        return super().format(record)


_FILE_FORMAT = _Formatter(
    "[%(asctime)s.%(msecs)03d] %(levelname)-7s %(threadName)-13s %(short_name)s: %(message)s", _DATE_FORMAT
)
_CONSOLE_FORMAT = _Formatter("[%(levelname)s] %(short_name)s: %(message)s")


def configure_logging(log_dir: Path | None = None, debug: bool = False) -> None:
    """Configura el logger ``pdfmanagement`` y captura excepciones no controladas."""
    log_dir = log_dir or paths.LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(ROOT_LOGGER)
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
        console_handler.set_name("console")
        console_handler.setFormatter(_CONSOLE_FORMAT)
        logger.addHandler(console_handler)

    set_debug(debug or debug_requested_by_env())

    def log_uncaught(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical("Excepcion no controlada", exc_info=(exc_type, exc_value, exc_traceback))

    def log_thread_exception(args: threading.ExceptHookArgs) -> None:
        logger.critical(
            "Excepcion no controlada en el hilo %s",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),  # type: ignore[arg-type]  # exc_value puede ser None
        )

    sys.excepthook = log_uncaught
    threading.excepthook = log_thread_exception


def set_debug(enabled: bool) -> None:
    """
    Activa o desactiva el modo detallado en caliente: el archivo pasa a DEBUG
    y la consola muestra todo (o solo advertencias y errores).
    """
    logger = logging.getLogger(ROOT_LOGGER)
    logger.setLevel(logging.DEBUG if enabled else logging.INFO)
    for handler in logger.handlers:
        if handler.get_name() == "console":
            handler.setLevel(logging.DEBUG if enabled else logging.WARNING)


def is_debug() -> bool:
    return logging.getLogger(ROOT_LOGGER).isEnabledFor(logging.DEBUG)


def debug_requested_by_env() -> bool:
    return os.environ.get(DEBUG_ENV_VAR, "").strip().lower() in ("1", "true", "yes", "si", "on")


def app_log_file() -> Path:
    return paths.LOG_DIR / "app.log"
