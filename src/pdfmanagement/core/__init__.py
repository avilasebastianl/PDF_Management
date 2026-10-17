"""
Nucleo de operaciones PDF.

No depende de la interfaz grafica: cada funcion recibe rutas y parametros,
escribe el resultado de forma atomica y devuelve la ruta generada. Los errores
esperados se lanzan como subclases de ``PdfManagementError``.
"""

from .convert import OFFICE_EXTENSIONS, convert_to_pdf
from .documents import PdfInfo, get_pdf_info, open_document
from .errors import (
    ConversionError,
    InvalidInputError,
    OutputError,
    PasswordRequiredError,
    PdfManagementError,
    WrongPasswordError,
)
from .extract import extract_pages
from .files import IMAGE_EXTENSIONS, PDF_EXTENSIONS, unique_path
from .merge import merge_pdfs
from .pages import parse_page_selection
from .security import MIN_PASSWORD_LENGTH, lock_pdf, unlock_pdf
from .signing import (
    DEFAULT_SIGNATURE_WIDTH,
    SignaturePlacement,
    image_aspect_ratio,
    load_signature,
    resolve_page_index,
    sign_pdf_with_image,
    signature_rect,
)

__all__ = [
    "ConversionError",
    "DEFAULT_SIGNATURE_WIDTH",
    "IMAGE_EXTENSIONS",
    "InvalidInputError",
    "MIN_PASSWORD_LENGTH",
    "OFFICE_EXTENSIONS",
    "OutputError",
    "PDF_EXTENSIONS",
    "PasswordRequiredError",
    "PdfInfo",
    "PdfManagementError",
    "SignaturePlacement",
    "WrongPasswordError",
    "convert_to_pdf",
    "extract_pages",
    "get_pdf_info",
    "image_aspect_ratio",
    "load_signature",
    "lock_pdf",
    "merge_pdfs",
    "open_document",
    "parse_page_selection",
    "resolve_page_index",
    "sign_pdf_with_image",
    "signature_rect",
    "unique_path",
    "unlock_pdf",
]
