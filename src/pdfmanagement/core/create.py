"""
Documentos nuevos: en blanco o desde una plantilla (renglones, cuadricula,
carta, acta de reunion y factura).

Las plantillas se dibujan con PyMuPDF (sin archivos externos) y sus textos
salen en el idioma de la interfaz. Para textos que Helvetica no puede escribir
(cirilico) se usa Arial, igual que en Herramientas.
"""

from dataclasses import dataclass
from pathlib import Path

import pymupdf

from ..i18n import tr
from .editing.content import helvetica_can_write
from .errors import InvalidInputError
from .files import atomic_output
from .tools import UNICODE_FONT

TEMPLATES = ("blank", "lined", "grid", "letter", "minutes", "invoice")
MULTI_PAGE = ("blank", "lined", "grid")  # las demas plantillas son de una pagina
PAGE_SIZES = {"A4": (595.0, 842.0), "Carta": (612.0, 792.0), "Oficio": (612.0, 1008.0)}
MAX_PAGES = 500
MARGIN = 56
LINE = (0.72, 0.75, 0.80)  # renglones y bordes
HEADING = (0.12, 0.25, 0.45)  # titulos
TEXT = (0.15, 0.15, 0.15)
MUTED = (0.42, 0.42, 0.45)
UNICODE_BOLD_FONT = UNICODE_FONT.with_name("arialbd.ttf")


def template_names() -> dict[str, str]:
    """Clave interna -> nombre que se muestra (en el idioma de la interfaz)."""
    return {
        "blank": tr("En blanco"),
        "lined": tr("Hoja con renglones"),
        "grid": tr("Cuadrícula"),
        "letter": tr("Carta"),
        "minutes": tr("Acta de reunión"),
        "invoice": tr("Factura"),
    }


def size_names() -> dict[str, str]:
    """Clave interna -> nombre del tamano de papel que se muestra."""
    return {"A4": "A4", "Carta": tr("Carta (Letter)"), "Oficio": tr("Oficio (Legal)")}


@dataclass(frozen=True)
class NewDocument:
    """Que documento crear."""

    template: str = "blank"
    size: str = "A4"
    landscape: bool = False
    pages: int = 1


def build_document(spec: NewDocument) -> pymupdf.Document:
    """Documento en memoria segun ``spec`` (tambien para la vista previa)."""
    if spec.template not in TEMPLATES:
        raise InvalidInputError(tr("Plantilla desconocida: {nombre}", nombre=spec.template))
    if spec.size not in PAGE_SIZES:
        raise InvalidInputError(tr("Tamaño de papel desconocido: {nombre}", nombre=spec.size))
    if not 1 <= spec.pages <= MAX_PAGES:
        raise InvalidInputError(tr("El número de páginas debe estar entre 1 y {maximo}.", maximo=MAX_PAGES))
    width, height = PAGE_SIZES[spec.size]
    if spec.landscape:
        width, height = height, width
    count = spec.pages if spec.template in MULTI_PAGE else 1
    document = pymupdf.open()
    for _ in range(count):
        page = document.new_page(width=width, height=height)
        DRAWERS[spec.template](page)
    document.set_metadata({"title": template_names()[spec.template], "creator": "PDF Management"})
    return document


def create_document(output_file: str | Path, spec: NewDocument) -> Path:
    """Crea el PDF en ``output_file`` (escritura atomica) y devuelve su ruta."""
    output = Path(output_file)
    document = build_document(spec)
    try:
        with atomic_output(output) as temporary:
            document.save(temporary, garbage=3, deflate=True)
    finally:
        document.close()
    return output


# * Plantillas ---------------------------------------------------------------------


def _blank(page: pymupdf.Page) -> None:
    del page


def _lined(page: pymupdf.Page) -> None:
    rect = page.rect
    y = MARGIN + 28.0
    while y < rect.height - MARGIN:
        page.draw_line((MARGIN, y), (rect.width - MARGIN, y), color=LINE, width=0.6)
        y += 24
    page.draw_line((MARGIN + 36, MARGIN), (MARGIN + 36, rect.height - MARGIN), color=(0.9, 0.55, 0.55), width=0.6)


def _grid(page: pymupdf.Page) -> None:
    rect, step = page.rect, 14.17  # 5 mm
    x = MARGIN / 2
    while x <= rect.width - MARGIN / 2:
        page.draw_line((x, MARGIN / 2), (x, rect.height - MARGIN / 2), color=LINE, width=0.35)
        x += step
    y = MARGIN / 2
    while y <= rect.height - MARGIN / 2:
        page.draw_line((MARGIN / 2, y), (rect.width - MARGIN / 2, y), color=LINE, width=0.35)
        y += step


def _letter(page: pymupdf.Page) -> None:
    width = page.rect.width
    _write(page, (width - MARGIN - 180, MARGIN + 10), tr("Ciudad, fecha:"), 10, MUTED)
    _rule(page, width - MARGIN - 110, width - MARGIN, MARGIN + 12)
    y = MARGIN + 60
    for label in (tr("Destinatario:"), tr("Cargo / empresa:"), tr("Dirección:")):
        _write(page, (MARGIN, y), label, 10, MUTED)
        _rule(page, MARGIN + 110, width - MARGIN, y + 2)
        y += 24
    y += 16
    _write(page, (MARGIN, y), tr("Asunto:"), 11, HEADING, bold=True)
    _rule(page, MARGIN + 60, width - MARGIN, y + 2)
    y += 36
    _write(page, (MARGIN, y), tr("Estimado(a):"), 11, TEXT)
    y += 30
    bottom = page.rect.height - MARGIN - 110
    while y < bottom:
        _rule(page, MARGIN, width - MARGIN, y)
        y += 22
    _write(page, (MARGIN, bottom + 30), tr("Atentamente,"), 11, TEXT)
    _rule(page, MARGIN, MARGIN + 200, bottom + 84)
    _write(page, (MARGIN, bottom + 98), tr("Nombre y firma"), 9, MUTED)


def _minutes(page: pymupdf.Page) -> None:
    width = page.rect.width
    _title(page, tr("Acta de reunión"))
    y = MARGIN + 64
    for label in (tr("Fecha:"), tr("Hora:"), tr("Lugar:"), tr("Asistentes:")):
        _write(page, (MARGIN, y), label, 10, MUTED)
        _rule(page, MARGIN + 90, width - MARGIN, y + 2)
        y += 24
    for heading, rows in ((tr("Temas tratados"), 6), (tr("Acuerdos y responsables"), 6)):
        y += 18
        _write(page, (MARGIN, y), heading, 12, HEADING, bold=True)
        y += 16
        for number in range(1, rows + 1):
            _write(page, (MARGIN, y + 14), f"{number}.", 10, MUTED)
            _rule(page, MARGIN + 20, width - MARGIN, y + 16)
            y += 24
    y = max(y + 40, page.rect.height - MARGIN - 40)
    half = (width - 2 * MARGIN - 40) / 2
    for x in (MARGIN, MARGIN + half + 40):
        _rule(page, x, x + half, y)
        _write(page, (x, y + 14), tr("Firma"), 9, MUTED)


def _invoice(page: pymupdf.Page) -> None:
    width = page.rect.width
    _title(page, tr("Factura"))
    _write(page, (width - MARGIN - 150, MARGIN + 22), tr("N.º:"), 10, MUTED)
    _rule(page, width - MARGIN - 110, width - MARGIN, MARGIN + 24)
    _write(page, (width - MARGIN - 150, MARGIN + 46), tr("Fecha:"), 10, MUTED)
    _rule(page, width - MARGIN - 110, width - MARGIN, MARGIN + 48)
    y = MARGIN + 92
    half = (width - 2 * MARGIN - 30) / 2
    for column, heading in enumerate((tr("Emisor"), tr("Cliente"))):
        x = MARGIN + column * (half + 30)
        _write(page, (x, y), heading, 11, HEADING, bold=True)
        for row, label in enumerate((tr("Nombre:"), tr("Identificación:"), tr("Dirección:"), tr("Teléfono:"))):
            line_y = y + 24 + row * 22
            _write(page, (x, line_y), label, 9, MUTED)
            _rule(page, x + 78, x + half, line_y + 2)
    y += 140
    columns = (tr("Descripción"), tr("Cantidad"), tr("Precio unitario"), tr("Total"))
    widths = (0.46, 0.14, 0.2, 0.2)
    table_width = width - 2 * MARGIN
    page.draw_rect((MARGIN, y, width - MARGIN, y + 24), color=None, fill=(0.93, 0.95, 0.98))
    x = MARGIN
    for title, share in zip(columns, widths, strict=True):
        _write(page, (x + 6, y + 16), title, 9, HEADING, bold=True)
        x += table_width * share
    rows = 12
    for row in range(rows + 1):
        line_y = y + 24 + row * 22
        page.draw_line((MARGIN, line_y), (width - MARGIN, line_y), color=LINE, width=0.6)
    x = MARGIN
    for share in (0.0, *widths):
        x += table_width * share
        page.draw_line((x, y), (x, y + 24 + rows * 22), color=LINE, width=0.6)
    y += 24 + rows * 22 + 26
    for label in (tr("Subtotal"), tr("Impuestos"), tr("Total a pagar")):
        _write(page, (width - MARGIN - 200, y), label, 10, TEXT, bold=label == tr("Total a pagar"))
        _rule(page, width - MARGIN - 100, width - MARGIN, y + 2)
        y += 22


DRAWERS = {
    "blank": _blank,
    "lined": _lined,
    "grid": _grid,
    "letter": _letter,
    "minutes": _minutes,
    "invoice": _invoice,
}


# * Dibujo -------------------------------------------------------------------------


def _title(page: pymupdf.Page, text: str) -> None:
    _write(page, (MARGIN, MARGIN + 24), text, 20, HEADING, bold=True)
    page.draw_line((MARGIN, MARGIN + 34), (page.rect.width - MARGIN, MARGIN + 34), color=HEADING, width=1.2)


def _rule(page: pymupdf.Page, x0: float, x1: float, y: float) -> None:
    page.draw_line((x0, y), (x1, y), color=LINE, width=0.6)


def _write(page: pymupdf.Page, point: tuple[float, float], text: str, size: float, color, bold: bool = False) -> None:
    """Texto con Helvetica si alcanza; si no (cirilico), con Arial."""
    if helvetica_can_write(text) or not UNICODE_FONT.exists():
        page.insert_text(point, text, fontsize=size, fontname="hebo" if bold else "helv", color=color)
        return
    font = UNICODE_BOLD_FONT if bold and UNICODE_BOLD_FONT.exists() else UNICODE_FONT
    page.insert_text(point, text, fontsize=size, fontname=font.stem, fontfile=str(font), color=color)
