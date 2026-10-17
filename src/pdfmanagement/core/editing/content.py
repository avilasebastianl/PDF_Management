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
    for rect in rects:
        page.add_redact_annot((rect * page.derotation_matrix).normalize(), fill=None)
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
    if new_text.strip():
        _write_lines(page, style.origin, new_text, style.fontsize, style.color, style.angle)


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


def redact(page: pymupdf.Page, rect: pymupdf.Rect, color: Color = (0.0, 0.0, 0.0)) -> None:
    """
    Tapa definitivamente lo que hay en ``rect``: borra texto, imagenes y
    dibujos de esa zona y la pinta de ``color``. No se puede recuperar desde
    el archivo guardado.
    """
    target = (pymupdf.Rect(rect) * page.derotation_matrix).normalize()
    if target.width < 2 or target.height < 2:
        raise InvalidInputError(tr("El área es demasiado pequeña: arrástrela para dibujarla."))
    page.add_redact_annot(target, fill=color)
    page.apply_redactions()


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
