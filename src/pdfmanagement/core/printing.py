"""
Impresion en Windows sin dependencias externas.

Muestra el dialogo de impresion nativo (impresora, paginas, copias) con
``PrintDlgW`` y dibuja cada pagina con GDI a la resolucion de la impresora,
ajustada al area imprimible y girada si la orientacion no coincide. Las copias
y el intercalado los maneja el controlador de la impresora.
"""

import ctypes
import logging
import sys
from collections.abc import Callable
from ctypes import wintypes
from dataclasses import dataclass

import pymupdf
from PIL import Image, ImageWin

from ..i18n import tr
from .errors import OutputError

logger = logging.getLogger(__name__)

MAX_DPI = 300  # mas no mejora el resultado y multiplica la memoria y el tiempo
PD_RETURNDC = 0x00000100
PD_PAGENUMS = 0x00000002
PD_NOSELECTION = 0x00000004
PD_USEDEVMODECOPIESANDCOLLATE = 0x00040000
HORZRES, VERTRES, LOGPIXELSX, LOGPIXELSY = 8, 10, 88, 90


class _PrintDlg(ctypes.Structure):
    _fields_ = [
        ("lStructSize", wintypes.DWORD),
        ("hwndOwner", wintypes.HWND),
        ("hDevMode", wintypes.HGLOBAL),
        ("hDevNames", wintypes.HGLOBAL),
        ("hDC", wintypes.HDC),
        ("Flags", wintypes.DWORD),
        ("nFromPage", wintypes.WORD),
        ("nToPage", wintypes.WORD),
        ("nMinPage", wintypes.WORD),
        ("nMaxPage", wintypes.WORD),
        ("nCopies", wintypes.WORD),
        ("hInstance", wintypes.HINSTANCE),
        ("lCustData", wintypes.LPARAM),
        ("lpfnPrintHook", ctypes.c_void_p),
        ("lpfnSetupHook", ctypes.c_void_p),
        ("lpPrintTemplateName", wintypes.LPCWSTR),
        ("lpSetupTemplateName", wintypes.LPCWSTR),
        ("hPrintTemplate", wintypes.HGLOBAL),
        ("hSetupTemplate", wintypes.HGLOBAL),
    ]


class _DocInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_int),
        ("lpszDocName", wintypes.LPCWSTR),
        ("lpszOutput", wintypes.LPCWSTR),
        ("lpszDatatype", wintypes.LPCWSTR),
        ("fwType", wintypes.DWORD),
    ]


@dataclass(frozen=True)
class Placement:
    """Donde va una pagina en el area imprimible (pixeles de la impresora)."""

    rotate: bool  # girar 90 grados para aprovechar el papel
    box: tuple[int, int, int, int]  # x0, y0, x1, y1


def fit_page(page_width: float, page_height: float, area_width: int, area_height: int) -> Placement:
    """Ajusta la pagina al area imprimible conservando la proporcion; gira si mejora el tamano."""
    rotate = (page_width > page_height) != (area_width > area_height)
    width, height = (page_height, page_width) if rotate else (page_width, page_height)
    scale = min(area_width / width, area_height / height)
    out_w, out_h = round(width * scale), round(height * scale)
    x0, y0 = (area_width - out_w) // 2, (area_height - out_h) // 2
    return Placement(rotate, (x0, y0, x0 + out_w, y0 + out_h))


def is_available() -> bool:
    return sys.platform.startswith("win")


def print_document(
    document: pymupdf.Document,
    title: str,
    owner: int = 0,
    progress: Callable[[int, int], None] | None = None,
) -> int | None:
    """
    Muestra el dialogo de impresion y envia las paginas elegidas. Devuelve
    cuantas se imprimieron o ``None`` si el usuario cancelo.
    """
    if not is_available():
        raise OutputError(tr("La impresión solo está disponible en Windows."))
    comdlg32, gdi32, kernel32 = ctypes.windll.comdlg32, ctypes.windll.gdi32, ctypes.windll.kernel32
    dialog = _PrintDlg()
    dialog.lStructSize = ctypes.sizeof(_PrintDlg)
    dialog.hwndOwner = owner
    dialog.Flags = PD_RETURNDC | PD_USEDEVMODECOPIESANDCOLLATE | PD_NOSELECTION
    dialog.nMinPage, dialog.nMaxPage = 1, document.page_count
    dialog.nFromPage, dialog.nToPage = 1, document.page_count
    dialog.nCopies = 1
    if not comdlg32.PrintDlgW(ctypes.byref(dialog)):
        error = comdlg32.CommDlgExtendedError()
        if error:
            raise OutputError(tr("No se pudo abrir el diálogo de impresión (código {code}).", code=error))
        return None  # cancelado
    hdc = dialog.hDC
    try:
        first, last = 0, document.page_count - 1
        if dialog.Flags & PD_PAGENUMS:
            first, last = dialog.nFromPage - 1, min(dialog.nToPage, document.page_count) - 1
        return _print_pages(gdi32, hdc, document, title, range(first, last + 1), progress)
    finally:
        gdi32.DeleteDC(hdc)
        for handle in (dialog.hDevMode, dialog.hDevNames):
            if handle:
                kernel32.GlobalFree(handle)


def _print_pages(gdi32, hdc, document, title: str, pages: range, progress) -> int:
    area_w, area_h = gdi32.GetDeviceCaps(hdc, HORZRES), gdi32.GetDeviceCaps(hdc, VERTRES)
    dpi = min(gdi32.GetDeviceCaps(hdc, LOGPIXELSX), gdi32.GetDeviceCaps(hdc, LOGPIXELSY), MAX_DPI)
    info = _DocInfo()
    info.cbSize = ctypes.sizeof(_DocInfo)
    info.lpszDocName = title
    if gdi32.StartDocW(hdc, ctypes.byref(info)) <= 0:
        raise OutputError(tr("La impresora rechazó el trabajo de impresión."))
    printed = 0
    try:
        for count, index in enumerate(pages, start=1):
            page = document[index]
            placement = fit_page(page.rect.width, page.rect.height, area_w, area_h)
            pixmap = page.get_pixmap(dpi=dpi, alpha=False)
            image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
            if placement.rotate:
                image = image.rotate(90, expand=True)
            if gdi32.StartPage(hdc) <= 0:
                raise OutputError(tr("La impresora rechazó la página {number}.", number=index + 1))
            ImageWin.Dib(image).draw(hdc, placement.box)
            gdi32.EndPage(hdc)
            printed += 1
            if progress:
                progress(count, len(pages))
    except Exception:
        gdi32.AbortDoc(hdc)
        raise
    gdi32.EndDoc(hdc)
    logger.info("Impresas %d paginas de %s", printed, title)
    return printed
