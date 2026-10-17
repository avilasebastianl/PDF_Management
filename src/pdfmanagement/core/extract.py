"""
Extraccion de paginas de un PDF a un archivo nuevo.
"""

import logging
from pathlib import Path

from pypdf import PdfWriter

from .documents import open_reader
from .files import PDF_EXTENSIONS, atomic_output, prepare_output, require_file
from .pages import parse_page_selection
from .security import ENCRYPTION_ALGORITHM

logger = logging.getLogger(__name__)


def extract_pages(
    input_file: str | Path,
    output_file: str | Path,
    selection: str,
    *,
    password: str | None = None,
    output_password: str | None = None,
) -> Path:
    """
    Copia las paginas seleccionadas a un PDF nuevo, en el orden indicado.

    Args:
        input_file: PDF de origen.
        output_file: PDF a generar.
        selection: Paginas desde 1 (ver ``pages.parse_page_selection``).
        password: Contrasena del PDF de origen, si la tiene.
        output_password: Si se indica, el PDF generado se protege (AES-256).

    Returns:
        Ruta del PDF generado.
    """
    source = require_file(input_file, PDF_EXTENSIONS)
    output_path = prepare_output(output_file, source)
    reader = open_reader(source, password)
    indexes = parse_page_selection(selection, len(reader.pages))

    writer = PdfWriter()
    try:
        for index in indexes:
            writer.add_page(reader.pages[index])
        if output_password:
            writer.encrypt(output_password, output_password, algorithm=ENCRYPTION_ALGORITHM)
        with atomic_output(output_path) as temp_path:
            writer.write(temp_path)
    finally:
        writer.close()

    logger.info("Extraidas %d paginas de %s: %s", len(indexes), source.name, output_path)
    return output_path
