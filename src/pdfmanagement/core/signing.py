"""
Firma visual: estampa una imagen de firma sobre una o varias paginas.

Esta firma es grafica (no criptografica). El sistema de coordenadas es el de
la pagina tal como se ve en pantalla: origen arriba a la izquierda, unidades en
puntos PDF (72 puntos = 1 pulgada). Las paginas rotadas se manejan de forma
transparente, por lo que la vista previa y el resultado siempre coinciden.
"""

import io
import logging
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PIL import Image

from .documents import open_document
from .errors import InvalidInputError
from .files import IMAGE_EXTENSIONS, PDF_EXTENSIONS, atomic_output, prepare_output, require_file

logger = logging.getLogger(__name__)

DEFAULT_SIGNATURE_WIDTH = 150.0
MIN_SIGNATURE_WIDTH = 20.0


@dataclass(frozen=True)
class SignaturePlacement:
    """
    Posicion de la firma.

    Attributes:
        x: Borde izquierdo en puntos, sobre la pagina tal como se visualiza.
        y: Borde superior en puntos.
        width: Ancho de la firma en puntos; el alto se deriva de la imagen.
        page_number: Pagina desde 1. ``None`` significa la ultima pagina.
        all_pages: Estampa la firma en la misma posicion en todas las paginas.
    """

    x: float
    y: float
    width: float = DEFAULT_SIGNATURE_WIDTH
    page_number: int | None = None
    all_pages: bool = False


PAPER_THRESHOLD = 235  # brillo a partir del cual un pixel se considera papel


def load_signature(image_path: str | Path) -> Image.Image:
    """
    Carga la imagen de firma lista para estampar (RGBA):

    - Si la imagen no tiene transparencia (foto o escaneo), el fondo claro se
      vuelve transparente para no tapar el contenido del PDF.
    - Se recortan los margenes vacios para que el ancho indicado corresponda
      al trazo y no al lienzo.
    """
    path = require_file(image_path, IMAGE_EXTENSIONS)
    with Image.open(path) as source:
        image = source.convert("RGBA")
    if image.getchannel("A").getextrema()[0] == 255:
        brightness = image.convert("L")
        image.putalpha(
            brightness.point(lambda value: 0 if value >= PAPER_THRESHOLD else min(255, (PAPER_THRESHOLD - value) * 4))
        )
    bbox = image.getchannel("A").getbbox()
    if not bbox:
        raise InvalidInputError("La imagen de firma esta vacia.")
    return image.crop(bbox)


def image_aspect_ratio(image: Image.Image) -> float:
    """Relacion alto/ancho de la imagen de firma."""
    return image.height / image.width


def signature_rect(page_rect: pymupdf.Rect, placement: SignaturePlacement, aspect_ratio: float) -> pymupdf.Rect:
    """
    Calcula el rectangulo visible de la firma, ajustado para no salir de la
    pagina. Lo usan tanto la vista previa como la estampa final.
    """
    width = max(MIN_SIGNATURE_WIDTH, min(placement.width, page_rect.width))
    height = width * aspect_ratio
    if height > page_rect.height:
        height = page_rect.height
        width = height / aspect_ratio
    x = min(max(placement.x, 0.0), page_rect.width - width)
    y = min(max(placement.y, 0.0), page_rect.height - height)
    return pymupdf.Rect(x, y, x + width, y + height)


def resolve_page_index(page_number: int | None, page_count: int) -> int:
    """Convierte una pagina desde 1 (o ``None`` = ultima) a indice base cero."""
    if page_number is None:
        return page_count - 1
    if not 1 <= page_number <= page_count:
        raise InvalidInputError(f"La pagina {page_number} no existe. El PDF tiene {page_count} paginas.")
    return page_number - 1


def sign_pdf_with_image(
    input_file: str | Path,
    output_file: str | Path,
    signature_image: str | Path,
    placement: SignaturePlacement,
    *,
    password: str | None = None,
) -> Path:
    """
    Estampa la imagen de firma y guarda el resultado.

    Si el PDF de origen esta protegido, el resultado conserva su proteccion.

    Returns:
        Ruta del PDF firmado.
    """
    source = require_file(input_file, PDF_EXTENSIONS)
    output_path = prepare_output(output_file, source)
    image = load_signature(signature_image)
    aspect_ratio = image_aspect_ratio(image)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    image_bytes = buffer.getvalue()

    with open_document(source, password) as document:
        if placement.all_pages:
            pages = list(document)
        else:
            pages = [document[resolve_page_index(placement.page_number, document.page_count)]]

        image_xref = 0
        for page in pages:
            visible_rect = signature_rect(page.rect, placement, aspect_ratio)
            # ``insert_image`` trabaja en coordenadas de la pagina sin rotar.
            image_xref = page.insert_image(
                visible_rect * page.derotation_matrix,
                stream=image_bytes if not image_xref else None,
                xref=image_xref,
                rotate=page.rotation,
            )

        # KEEP conserva el cifrado original; en PDFs sin proteccion no tiene efecto.
        with atomic_output(output_path) as temp_path:
            document.save(temp_path, garbage=3, deflate=True, encryption=pymupdf.PDF_ENCRYPT_KEEP)

    logger.info("PDF firmado (%d paginas): %s", len(pages), output_path)
    return output_path
