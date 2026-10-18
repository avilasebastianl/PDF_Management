"""
Terminaciones de un PDF ya generado: marca de agua y firma (visual o digital).

Las usa Unir para entregar el resultado listo en un solo paso, con las mismas
funciones que Herramientas (marca de agua) y Firmar (firmas). Tambien dibuja la
vista previa de una pagina con esas terminaciones, sin guardar nada.

Orden al aplicar: marca de agua, firma visual y, al final, la firma digital
(cualquier cambio posterior la invalidaria).
"""

import io
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PIL import Image

from ..i18n import tr
from . import tools
from .digital_signing import sign_pdf_with_certificate
from .documents import open_document
from .errors import InvalidInputError
from .files import PDF_EXTENSIONS, atomic_output, require_file
from .signing import SignaturePlacement, image_aspect_ratio, load_signature, sign_pdf_with_image

# Posicion de la firma -> (horizontal, vertical); el margen es SIGNATURE_MARGIN.
POSITIONS = {
    "abajo-derecha": ("derecha", "abajo"),
    "abajo-centro": ("centro", "abajo"),
    "abajo-izquierda": ("izquierda", "abajo"),
    "arriba-derecha": ("derecha", "arriba"),
    "arriba-izquierda": ("izquierda", "arriba"),
}
PAGES = ("ultima", "primera", "todas")
SIGNATURE_MARGIN = 36.0
DIGITAL_ASPECT = 0.4  # alto/ancho del sello de la firma digital


@dataclass(frozen=True)
class WatermarkOptions:
    text: str
    opacity: float = 0.15
    angle: float = 45
    behind: bool = False


@dataclass(frozen=True)
class SignatureOptions:
    """Firma visual (``image``) o digital (``certificate``) en una posicion fija."""

    kind: str  # "visual" o "digital"
    position: str = "abajo-derecha"
    pages: str = "ultima"  # "ultima", "primera" o "todas" (la digital, una sola pagina)
    width: float = 150.0
    image: Path | None = None
    certificate: Path | None = None
    certificate_password: str | None = None


def target_page(pages: str, page_count: int) -> int:
    """Indice de la pagina donde va la firma (la de la vista previa)."""
    return 0 if pages == "primera" else page_count - 1


def placement_for(page_rect: pymupdf.Rect, options: SignatureOptions, aspect: float) -> SignaturePlacement:
    """Ubicacion de la firma en la pagina segun su posicion predefinida."""
    horizontal, vertical = POSITIONS.get(options.position, POSITIONS["abajo-derecha"])
    width = min(options.width, page_rect.width - 2 * SIGNATURE_MARGIN)
    height = width * aspect
    x = {
        "izquierda": SIGNATURE_MARGIN,
        "centro": (page_rect.width - width) / 2,
        "derecha": page_rect.width - SIGNATURE_MARGIN - width,
    }[horizontal]
    y = SIGNATURE_MARGIN if vertical == "arriba" else page_rect.height - SIGNATURE_MARGIN - height
    page_number = None if options.pages != "primera" else 1
    return SignaturePlacement(x, y, width, page_number=page_number, all_pages=options.pages == "todas")


def _aspect(options: SignatureOptions) -> float:
    if options.kind == "visual":
        if options.image is None:
            raise InvalidInputError(tr("Elija la imagen de la firma."))
        return image_aspect_ratio(load_signature(options.image))
    return DIGITAL_ASPECT


def apply_finish(
    pdf_file: str | Path,
    watermark: WatermarkOptions | None = None,
    signature: SignatureOptions | None = None,
) -> Path:
    """Agrega la marca de agua y la firma a ``pdf_file`` (lo reemplaza de forma atomica)."""
    path = require_file(pdf_file, PDF_EXTENSIONS)
    if watermark is None and signature is None:
        return path
    if signature is not None and signature.kind == "digital" and signature.certificate is None:
        raise InvalidInputError(tr("Elija el certificado digital (.pfx o .p12)."))
    folder = Path(tempfile.mkdtemp(prefix="pdfmanagement_terminar_"))
    try:
        current = path
        if watermark is not None and watermark.text.strip():
            current = tools.add_watermark(
                current,
                folder / "1_marca.pdf",
                watermark.text,
                opacity=watermark.opacity,
                angle=watermark.angle,
                behind=watermark.behind,
            )
        if signature is not None:
            with open_document(current) as document:
                page_rect = document[target_page(signature.pages, document.page_count)].rect
            placement = placement_for(page_rect, signature, _aspect(signature))
            if signature.kind == "visual":
                assert signature.image is not None
                current = sign_pdf_with_image(current, folder / "2_firma.pdf", signature.image, placement)
            else:
                assert signature.certificate is not None
                digital = SignaturePlacement(placement.x, placement.y, placement.width, placement.page_number)
                current = sign_pdf_with_certificate(
                    current,
                    folder / "3_firma_digital.pdf",
                    signature.certificate,
                    signature.certificate_password,
                    placement=digital,
                )
        with atomic_output(path) as temporary:
            shutil.copyfile(current, temporary)
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return path


def preview(
    pdf_file: str | Path,
    page_index: int,
    *,
    watermark: WatermarkOptions | None = None,
    signature: SignatureOptions | None = None,
    height: int = 420,
    password: str | None = None,
) -> Image.Image:
    """Imagen de una pagina de ``pdf_file`` con la marca de agua y la firma como quedaran."""
    source = require_file(pdf_file, PDF_EXTENSIONS)
    with open_document(source, password) as original:
        if not original.page_count:
            raise InvalidInputError(tr("El PDF no tiene páginas."))
        if page_index < 0:  # -1 = ultima pagina
            page_index += original.page_count
        index = max(0, min(page_index, original.page_count - 1))
        document = pymupdf.open()
        document.insert_pdf(original, from_page=index, to_page=index)
    try:
        page = document[0]
        if watermark is not None and watermark.text.strip():
            tools.stamp_watermark(
                page, watermark.text.strip(), 60, watermark.opacity, watermark.angle, watermark.behind
            )
        if signature is not None:
            _draw_signature(page, signature)
        zoom = height / page.rect.height
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    finally:
        document.close()


def _draw_signature(page: pymupdf.Page, signature: SignatureOptions) -> None:
    """Firma de muestra en la vista previa: la imagen elegida o el sello de la firma digital."""
    if signature.kind == "visual" and signature.image is not None:
        image = load_signature(signature.image)
        placement = placement_for(page.rect, signature, image_aspect_ratio(image))
        rect = pymupdf.Rect(
            placement.x,
            placement.y,
            placement.x + placement.width,
            placement.y + placement.width * image_aspect_ratio(image),
        )
        buffer = _png(image)
        page.insert_image(rect * page.derotation_matrix, stream=buffer, rotate=page.rotation)
        return
    placement = placement_for(page.rect, signature, DIGITAL_ASPECT)
    rect = pymupdf.Rect(
        placement.x, placement.y, placement.x + placement.width, placement.y + placement.width * DIGITAL_ASPECT
    )
    page.draw_rect(rect * page.derotation_matrix, color=(0.12, 0.35, 0.65), fill=(0.93, 0.96, 1.0), width=0.8)
    label = tr("Firma digital") if signature.kind == "digital" else tr("Firma")
    font = tools.TextFont.for_text(label)  # Arial si el texto no es latino (ruso)
    page.insert_textbox(
        (rect + (4, 4, -4, -4)) * page.derotation_matrix,
        label,
        fontsize=max(6.0, rect.height / 4),
        fontname=font.name,
        fontfile=font.file,
        color=(0.12, 0.35, 0.65),
        align=1,
        rotate=page.rotation,
    )


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
