"""
Edicion del contenido de la pagina (fase 4): reemplazar texto, agregar texto
e imagenes fijos y tapar informacion de forma definitiva.

A diferencia de las anotaciones, esto cambia el contenido mismo de la pagina:
lo que se tapa o reemplaza desaparece de verdad (ya no se puede copiar ni
buscar). Coordenadas de la pagina tal como se ve; todo funciona dentro de
``History.operation`` (verificado: insertar texto e imagenes y aplicar
redacciones se deshace sin problemas).

Limitacion: el texto nuevo se escribe con Helvetica (la fuente original suele
venir incrustada y recortada, sin todas las letras), del tamano y color del
texto que reemplaza.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from ...i18n import tr
from ..errors import InvalidInputError
from . import engine

Color = tuple[float, float, float]
LINE_HEIGHT = 1.2


@dataclass(frozen=True)
class TextStyle:
    """Tamano, color y linea base del texto original (coordenadas visibles)."""

    fontsize: float
    color: Color
    origin: pymupdf.Point
    angle: int = 0  # direccion del texto tal como se ve: 0, 90, 180 o 270 (antihorario)


def text_style_at(page: pymupdf.Page, rect: pymupdf.Rect) -> TextStyle:
    """Estilo del primer fragmento de texto dentro de ``rect`` (o uno por defecto)."""
    textpage = engine.visible_textpage(page, 0)
    for block in textpage.extractDICT().get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if pymupdf.Rect(span["bbox"]).intersects(rect) and span["text"].strip():
                    value = span["color"]
                    color = ((value >> 16) & 255) / 255, ((value >> 8) & 255) / 255, (value & 255) / 255
                    cos, sin = line.get("dir", (1, 0))
                    angle = round(math.degrees(math.atan2(-sin, cos)) / 90) * 90 % 360
                    return TextStyle(span["size"], color, pymupdf.Point(span["origin"]), angle)
    return TextStyle(11.0, (0.0, 0.0, 0.0), pymupdf.Point(rect.x0, rect.y1 - 2))


# * Colores tal como se ven ------------------------------------------------------

MIN_CONTRAST = 2.0  # por debajo, el color declarado no se distingue del fondo


def visible_colors(page: pymupdf.Page, rect: pymupdf.Rect) -> tuple[Color, Color | None]:
    """
    ``(fondo, texto)`` de la zona ``rect`` (coordenadas visibles) segun como se
    ve la pagina dibujada, no segun lo que declara el PDF. El fondo es el color
    mas comun de la zona; el texto, el que mas se aleja de el
    (``None`` si la zona es lisa).
    """
    area = pymupdf.Rect(rect) + (-2, -2, 2, 2)
    area &= page.rect
    if area.is_empty:
        return (1.0, 1.0, 1.0), None
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=area, alpha=False, annots=False)
    width, height, samples = pixmap.width, pixmap.height, pixmap.samples
    if width < 3 or height < 3:
        return (1.0, 1.0, 1.0), None

    def pixel(x: int, y: int) -> tuple[int, int, int]:
        offset = (y * width + x) * 3
        return samples[offset], samples[offset + 1], samples[offset + 2]

    # El fondo es el color que mas ocupa la zona: el texto ocupa poco y las lineas de un
    # recuadro ajustado (celdas de una tabla) tambien. Mirar solo el contorno tomaba el
    # borde negro de la celda como fondo y el texto nuevo salia blanco sobre blanco.
    every = [pixel(x, y) for y in range(height) for x in range(width)]
    counts: dict[tuple[int, int, int], int] = {}
    for color in every:
        key = (color[0] // 16, color[1] // 16, color[2] // 16)
        counts[key] = counts.get(key, 0) + 1
    common = max(counts, key=lambda key: counts[key])
    matching = [color for color in every if (color[0] // 16, color[1] // 16, color[2] // 16) == common]
    background = tuple(sum(channel) / len(matching) for channel in zip(*matching, strict=True))

    def distance(color) -> float:
        return sum((a - b) ** 2 for a, b in zip(color, background, strict=True)) ** 0.5

    inside = [pixel(x, y) for y in range(1, height - 1) for x in range(1, width - 1)]
    farthest = max((distance(color) for color in inside), default=0.0)
    background_rgb = (background[0] / 255, background[1] / 255, background[2] / 255)
    if farthest < 40:
        return background_rgb, None
    ink = [color for color in inside if distance(color) >= farthest * 0.7]  # sin los bordes suavizados
    text = tuple(sum(channel) / len(ink) / 255 for channel in zip(*ink, strict=True))
    return background_rgb, (text[0], text[1], text[2])


def contrast(first: Color, second: Color) -> float:
    """Relacion de contraste WCAG entre dos colores (1 = iguales, 21 = negro sobre blanco)."""

    def luminance(color: Color) -> float:
        channels = [value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4 for value in color]
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


# * Elementos de la pagina ---------------------------------------------------------


@dataclass(frozen=True)
class PageElement:
    """Algo que se ve en la pagina y se puede seleccionar: una linea de texto o una imagen."""

    kind: str  # "text" o "image"
    rect: pymupdf.Rect  # coordenadas visibles
    text: str = ""


def page_elements(page: pymupdf.Page) -> list[PageElement]:
    """Lineas de texto e imagenes de la pagina, en coordenadas visibles (sin modificar el documento)."""
    elements: list[PageElement] = []
    for block in engine.visible_textpage(page, 0).extractDICT().get("blocks", []):
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line.get("spans", [])).strip()
            if text:
                elements.append(PageElement("text", pymupdf.Rect(line["bbox"]), text))
    # Las imagenes, con los bloques (sin sus pixeles: extractDICT los copiaria todos).
    for block in engine.visible_textpage(page, pymupdf.TEXT_PRESERVE_IMAGES).extractBLOCKS():
        if block[6] == 1:
            rect = pymupdf.Rect(block[:4]) & page.rect
            if not rect.is_empty:
                elements.append(PageElement("image", rect))
    return elements


def remove_image(page: pymupdf.Page, rect: pymupdf.Rect) -> None:
    """Quita las imagenes que hay en ``rect`` sin tocar el texto ni los dibujos de encima."""
    target = (pymupdf.Rect(rect) * page.derotation_matrix).normalize()
    page.add_redact_annot(target, fill=None)
    page.apply_redactions(
        images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
        graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
        text=pymupdf.PDF_REDACT_TEXT_NONE,
    )


def helvetica_can_write(text: str) -> bool:
    """Helvetica (la letra de los textos nuevos) solo tiene el alfabeto latino (Windows-1252)."""
    try:
        text.encode("cp1252")
    except UnicodeEncodeError:
        return False
    return True


def _require_latin(text: str) -> None:
    # Dentro del historial solo se puede usar Helvetica (ver engine, punto 7).
    if not helvetica_can_write(text):
        raise InvalidInputError(
            tr(
                "El texto tiene caracteres que la letra Helvetica no puede escribir (por ejemplo, "
                "el alfabeto cirílico). Use solo letras latinas."
            )
        )


def replace_text(page: pymupdf.Page, rects: Sequence[pymupdf.Rect], new_text: str) -> None:
    """
    Quita el texto que ocupan ``rects`` (sin tocar fondos ni imagenes) y
    escribe ``new_text`` en su lugar con el mismo tamano y color.
    """
    if not rects:
        raise InvalidInputError(tr("Seleccione el texto que desea reemplazar."))
    _require_latin(new_text)
    rects = [pymupdf.Rect(rect) for rect in rects]
    style = text_style_at(page, rects[0])
    color = style.color
    # Algunos PDF declaran un color que no es el que se ve (p. ej. texto claro sobre
    # una franja oscura declarado negro): el texto nuevo quedaba como un bloque negro.
    background, ink = visible_colors(page, rects[0])
    if contrast(color, background) < MIN_CONTRAST:
        color = ink if ink is not None and contrast(ink, background) >= MIN_CONTRAST else _readable_on(background)
    for rect in rects:
        page.add_redact_annot((rect * page.derotation_matrix).normalize(), fill=None)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    if new_text.strip():
        _write_lines(page, style.origin, new_text, style.fontsize, color, style.angle)


def add_text(page: pymupdf.Page, point: tuple[float, float], text: str, fontsize: float, color: Color) -> None:
    """Texto fijo (parte del contenido); ``point`` es la esquina superior izquierda visible."""
    if not text.strip():
        raise InvalidInputError(tr("Escriba el texto que desea agregar."))
    _require_latin(text)
    origin = pymupdf.Point(point[0], point[1] + fontsize)
    _write_lines(page, origin, text, fontsize, color)


def add_image(page: pymupdf.Page, rect: pymupdf.Rect, image_file: str | Path) -> None:
    """Imagen fija en ``rect`` (se ajusta conservando la proporcion), derecha aunque la pagina este girada."""
    path = Path(image_file)
    if not path.is_file():
        raise InvalidInputError(tr("No se encontró la imagen '{name}'.", name=path.name))
    target = (pymupdf.Rect(rect) * page.derotation_matrix).normalize()
    if target.width < 4 or target.height < 4:
        raise InvalidInputError(tr("El área es demasiado pequeña: arrástrela para dibujarla."))
    try:
        page.insert_image(target, filename=str(path), rotate=page.rotation)
    except (RuntimeError, ValueError) as error:
        raise InvalidInputError(
            tr("No se pudo insertar la imagen '{name}': {error}", name=path.name, error=error)
        ) from error


def redact(page: pymupdf.Page, rect: pymupdf.Rect, color: Color | None = None) -> None:
    """
    Tapa definitivamente lo que hay en ``rect``: borra texto, imagenes y
    dibujos de esa zona y la pinta de ``color`` (por defecto, el color del
    fondo que la rodea: queda como borrado, sin un bloque negro). No se puede
    recuperar desde el archivo guardado.
    """
    target = (pymupdf.Rect(rect) * page.derotation_matrix).normalize()
    if target.width < 2 or target.height < 2:
        raise InvalidInputError(tr("El área es demasiado pequeña: arrástrela para dibujarla."))
    if color is None:
        color = visible_colors(page, pymupdf.Rect(rect))[0]
    page.add_redact_annot(target, fill=color)
    page.apply_redactions()


def _readable_on(background: Color) -> Color:
    """Negro o blanco, el que mejor se lea sobre ``background``."""
    black, white = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
    return black if contrast(black, background) >= contrast(white, background) else white


def _write_lines(
    page: pymupdf.Page, origin: pymupdf.Point, text: str, fontsize: float, color: Color, angle: int = 0
) -> None:
    """Escribe lineas desde ``origin`` en la direccion ``angle`` (como se ve), derechas respecto de ella."""
    engine.ensure_text_font(page)  # insert_font no funciona dentro del historial (engine, punto 7)
    derotate = page.derotation_matrix
    # Desplazamiento entre lineas: perpendicular a la direccion del texto (hacia "abajo" de ese texto).
    step = {0: (0, 1), 90: (1, 0), 180: (0, -1), 270: (-1, 0)}[angle]
    for index, line in enumerate(text.splitlines() or [""]):
        offset = index * fontsize * LINE_HEIGHT
        point = pymupdf.Point(origin.x + step[0] * offset, origin.y + step[1] * offset) * derotate
        rotate = (page.rotation + angle) % 360
        page.insert_text(point, line, fontsize=fontsize, fontname="helv", color=color, rotate=rotate)
