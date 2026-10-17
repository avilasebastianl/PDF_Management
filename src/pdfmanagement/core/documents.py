"""
Apertura de PDFs y lectura de metadatos, con manejo uniforme de contrasenas.
"""

from dataclasses import dataclass
from pathlib import Path

import pymupdf
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .errors import InvalidInputError, PasswordRequiredError, WrongPasswordError
from .files import PDF_EXTENSIONS, require_file


@dataclass(frozen=True)
class PdfInfo:
    """Resumen de un PDF para mostrar en la interfaz."""

    path: Path
    page_count: int | None
    size_bytes: int
    encrypted: bool


def open_reader(pdf_path: Path, password: str | None = None) -> PdfReader:
    """
    Abre un PDF con pypdf y lo descifra si es necesario.

    Primero intenta la contrasena vacia: muchos PDFs solo tienen contrasena de
    propietario (restricciones) y pueden leerse sin pedir nada al usuario.

    Raises:
        PasswordRequiredError: el PDF necesita contrasena y no se indico.
        WrongPasswordError: la contrasena indicada no es valida.
        InvalidInputError: el archivo no es un PDF legible.
    """
    try:
        reader = PdfReader(pdf_path)
    except (PdfReadError, ValueError, OSError) as error:
        raise InvalidInputError(f"No se pudo leer '{pdf_path.name}': {error}") from error

    if reader.is_encrypted and not reader.decrypt(""):
        if not password:
            raise PasswordRequiredError(pdf_path)
        if not reader.decrypt(password):
            raise WrongPasswordError(pdf_path)
    return reader


def open_document(pdf_path: Path, password: str | None = None) -> pymupdf.Document:
    """
    Equivalente a ``open_reader`` para PyMuPDF (render y edicion grafica).

    Tras autenticar no se debe volver a leer ``document.needs_pass``: MuPDF
    reintenta con contrasena vacia y el documento pasa a leerse en blanco.
    Para saber si estaba cifrado: ``document.metadata["encryption"]``.
    """
    try:
        document = pymupdf.open(pdf_path)
    except (pymupdf.FileDataError, RuntimeError) as error:
        raise InvalidInputError(f"No se pudo leer '{pdf_path.name}': {error}") from error

    if document.needs_pass and not document.authenticate(""):
        if not password:
            document.close()
            raise PasswordRequiredError(pdf_path)
        if not document.authenticate(password):
            document.close()
            raise WrongPasswordError(pdf_path)
    return document


def get_pdf_info(pdf_file: str | Path) -> PdfInfo:
    """Lee numero de paginas, tamano y estado de cifrado sin lanzar por contrasena."""
    path = require_file(pdf_file, PDF_EXTENSIONS)
    size_bytes = path.stat().st_size
    try:
        with pymupdf.open(path) as document:
            encrypted = bool(document.needs_pass)
            if encrypted and not document.authenticate(""):
                return PdfInfo(path, None, size_bytes, True)
            return PdfInfo(path, document.page_count, size_bytes, encrypted)
    except (pymupdf.FileDataError, RuntimeError) as error:
        raise InvalidInputError(f"No se pudo leer '{path.name}': {error}") from error
