"""
Union de varios PDFs en uno solo.
"""

import logging
from collections.abc import Iterable, Mapping
from pathlib import Path

from pypdf import PdfWriter

from ..i18n import tr
from .documents import open_reader
from .errors import InvalidInputError
from .files import PDF_EXTENSIONS, atomic_output, dedupe, prepare_output, require_file

logger = logging.getLogger(__name__)


def merge_pdfs(
    pdf_files: Iterable[str | Path],
    output_file: str | Path,
    *,
    passwords: Mapping[Path, str] | None = None,
    add_bookmarks: bool = False,
) -> Path:
    """
    Une los PDFs en el orden recibido y guarda el resultado.

    Args:
        pdf_files: Rutas de los PDFs a unir (los duplicados se ignoran).
        output_file: Ruta del PDF final.
        passwords: Contrasenas por archivo para PDFs protegidos.
        add_bookmarks: Si es ``True`` crea un marcador por archivo de origen;
            los marcadores originales quedan anidados debajo.

    Returns:
        Ruta del PDF generado.

    Raises:
        InvalidInputError: lista vacia o algun archivo invalido.
        PasswordRequiredError: algun PDF protegido no tiene contrasena (el
            atributo ``file_path`` indica cual).
    """
    sources = [require_file(path, PDF_EXTENSIONS) for path in dedupe(pdf_files)]
    if not sources:
        raise InvalidInputError(tr("Debe agregar al menos un PDF."))
    output_path = prepare_output(output_file, *sources)
    passwords = passwords or {}

    writer = PdfWriter()
    try:
        for source in sources:
            reader = open_reader(source, passwords.get(source))
            writer.append(reader, outline_item=source.stem if add_bookmarks else None)
        with atomic_output(output_path) as temp_path:
            writer.write(temp_path)
    finally:
        writer.close()

    logger.info("PDF unido (%d archivos): %s", len(sources), output_path)
    return output_path
