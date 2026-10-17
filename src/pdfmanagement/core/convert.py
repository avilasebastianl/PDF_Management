"""
Conversion de documentos de Office a PDF mediante automatizacion COM.

Requiere Windows con Microsoft Word / Excel instalados. ``comtypes`` se importa
de forma diferida para que el resto de la aplicacion funcione sin Office.
"""

import logging
from pathlib import Path

from ..i18n import tr
from .errors import ConversionError
from .files import atomic_output, prepare_output, require_file

logger = logging.getLogger(__name__)

WORD_EXTENSIONS = (".docx", ".doc", ".rtf")
EXCEL_EXTENSIONS = (".xlsx", ".xls")
OFFICE_EXTENSIONS = WORD_EXTENSIONS + EXCEL_EXTENSIONS

_WD_FORMAT_PDF = 17
_XL_TYPE_PDF = 0


def convert_to_pdf(input_file: str | Path, output_file: str | Path) -> Path:
    """
    Convierte un documento de Word o Excel a PDF segun su extension.

    Raises:
        InvalidInputError: archivo inexistente o extension no admitida.
        ConversionError: Office no esta disponible o fallo la exportacion.
    """
    source = require_file(input_file, OFFICE_EXTENSIONS)
    output_path = prepare_output(output_file, source)
    exporter = _export_word if source.suffix.lower() in WORD_EXTENSIONS else _export_excel

    with atomic_output(output_path) as temp_path:
        _run_com(exporter, source, temp_path)

    logger.info("Convertido %s a PDF: %s", source.name, output_path)
    return output_path


def _run_com(exporter, source: Path, target: Path) -> None:
    try:
        import comtypes
        import comtypes.client
    except ImportError as error:
        raise ConversionError(tr("La conversión requiere Windows con el paquete 'comtypes'.")) from error

    comtypes.CoInitialize()
    try:
        exporter(comtypes.client, source, target)
    except (OSError, comtypes.COMError) as error:
        raise ConversionError(
            tr(
                "No se pudo convertir '{name}'. Verifique que Microsoft Office esté instalado y que el archivo "
                "no esté dañado. Detalle: {error}",
                name=source.name,
                error=error,
            )
        ) from error
    finally:
        comtypes.CoUninitialize()


def _export_word(client, source: Path, target: Path) -> None:
    word = client.CreateObject("Word.Application")
    document = None
    try:
        word.Visible = False
        word.DisplayAlerts = 0
        document = word.Documents.Open(str(source), ConfirmConversions=False, ReadOnly=True, AddToRecentFiles=False)
        document.SaveAs(str(target), FileFormat=_WD_FORMAT_PDF)
    finally:
        if document is not None:
            document.Close(False)
        word.Quit()


def _export_excel(client, source: Path, target: Path) -> None:
    excel = client.CreateObject("Excel.Application")
    workbook = None
    try:
        excel.Visible = False
        excel.DisplayAlerts = False
        workbook = excel.Workbooks.Open(str(source), UpdateLinks=0, ReadOnly=True)
        workbook.ExportAsFixedFormat(_XL_TYPE_PDF, str(target))
    finally:
        if workbook is not None:
            workbook.Close(False)
        excel.Quit()


def is_supported(file_path: str | Path) -> bool:
    """Indica si la extension del archivo puede convertirse."""
    return Path(file_path).suffix.lower() in OFFICE_EXTENSIONS
