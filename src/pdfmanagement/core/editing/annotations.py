"""
Anotaciones: resaltar, subrayar y tachar texto, notas, texto libre, formas,
lineas, flechas y dibujo a mano.

Todas las coordenadas que reciben y devuelven estas funciones son de la
pagina **tal como se ve** (con su rotacion); aqui se convierten a las del PDF
con ``page.derotation_matrix``, asi el visor no necesita casos especiales para
paginas giradas (verificado en 0 y 90 grados).

Reglas verificadas con PyMuPDF 1.28 (todas dentro de ``History.operation``):

- Crear, cambiar color o texto y eliminar se deshacen sin problemas.
- ``Annot`` guarda una referencia debil a su ``Page``: la pagina debe seguir
  viva mientras se usa la anotacion (no encadenar ``document[i].add_...``).
- ``set_rect`` mueve texto libre, rectangulos y elipses (a estos hay que
  descontarles el borde, que ``annot.rect`` incluye y ``set_rect`` vuelve a
  sumar). No sirve para lineas ni dibujos, y en paginas giradas recoloca el
  icono de las notas: esos tres se mueven recreandolos con sus propiedades.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import pymupdf

from ..errors import InvalidInputError

Color = tuple[float, float, float]
Point = tuple[float, float]

LABELS = {
    "Highlight": "Resaltado",
    "Underline": "Subrayado",
    "StrikeOut": "Tachado",
    "Squiggly": "Ondulado",
    "Text": "Nota",
    "FreeText": "Texto",
    "Square": "Rectangulo",
    "Circle": "Elipse",
    "Line": "Linea",
    "Ink": "Dibujo",
    "Polygon": "Poligono",
    "PolyLine": "Polilinea",
    "Stamp": "Sello",
    "FileAttachment": "Archivo adjunto",
    "Caret": "Insercion",
    "Redact": "Tapado",
}
MARKUP_KINDS = {"Highlight", "Underline", "StrikeOut", "Squiggly"}
TEXT_KINDS = {"Text", "FreeText"}  # su contenido se ve o se edita como texto
RECT_KINDS = {"Square", "Circle", "FreeText", "Stamp"}  # se mueven con set_rect
RECREATE_KINDS = {"Text", "Line", "Ink"}  # se mueven recreandolas
BORDERED_KINDS = {"Square", "Circle"}  # annot.rect incluye el borde
HIDDEN_KINDS = {"Popup", "Link", "Widget"}

MARKUP_ADDERS = {
    "highlight": "add_highlight_annot",
    "underline": "add_underline_annot",
    "strikeout": "add_strikeout_annot",
}
DEFAULT_FONT_SIZE = 12
FONT_SIZES = (8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 40, 48)
LINE_HEIGHT = 1.2  # interlineado del texto libre de MuPDF (medido: 14,4 pt con letra de 12)
TEXT_PADDING = 4  # margen interno del cuadro de texto, en puntos
MAX_AUTO_WIDTH = 320  # ancho maximo de un cuadro creado con un clic


@dataclass(frozen=True)
class AnnotationStyle:
    """Color (RGB de 0 a 1), grosor del trazo en puntos y opacidad."""

    color: Color = (1.0, 0.85, 0.0)
    width: float = 2.0
    opacity: float = 1.0


@dataclass(frozen=True)
class AnnotationInfo:
    """Anotacion tal como la muestra el visor."""

    page: int
    xref: int
    kind: str  # tipo PDF: Highlight, Text, Square...
    rect: pymupdf.Rect  # coordenadas visibles
    content: str
    color: Color | None
    font_size: float | None = None  # solo texto libre

    @property
    def label(self) -> str:
        return LABELS.get(self.kind, self.kind)

    @property
    def movable(self) -> bool:
        return self.kind in RECT_KINDS or self.kind in RECREATE_KINDS

    @property
    def has_text(self) -> bool:
        return self.kind in TEXT_KINDS


# * Consultas -----------------------------------------------------------------


def list_annotations(page: pymupdf.Page, index: int) -> list[AnnotationInfo]:
    """Anotaciones visibles de la pagina (sin ventanas emergentes, enlaces ni campos)."""
    result = []
    for annot in page.annots():
        kind = annot.type[1]
        if kind in HIDDEN_KINDS:
            continue
        stroke = annot.colors.get("stroke") or annot.colors.get("fill")
        color = tuple(stroke[:3]) if stroke and len(stroke) >= 3 else None
        result.append(
            AnnotationInfo(
                page=index,
                xref=annot.xref,
                kind=kind,
                rect=annot.rect * page.rotation_matrix,
                content=(annot.info.get("content") or "").strip(),
                color=_free_text_color(annot) or color if kind == "FreeText" else color,
                font_size=font_size(annot) if kind == "FreeText" else None,
            )
        )
    return result


def find(page: pymupdf.Page, xref: int) -> pymupdf.Annot:
    for annot in page.annots():
        if annot.xref == xref:
            return annot
    raise InvalidInputError("La anotacion ya no existe en esta pagina.")


# * Crear ---------------------------------------------------------------------


def add_markup(page: pymupdf.Page, kind: str, rects: Sequence[pymupdf.Rect], style: AnnotationStyle) -> int:
    """Resalta, subraya o tacha el texto que ocupan ``rects`` (una por palabra o linea)."""
    if kind not in MARKUP_ADDERS:
        raise ValueError(f"Tipo de marca no valido: {kind}")
    if not rects:
        raise InvalidInputError("Seleccione el texto que desea marcar.")
    quads = [pymupdf.Rect(rect).quad * page.derotation_matrix for rect in rects]
    annot = getattr(page, MARKUP_ADDERS[kind])(quads=quads)
    _apply_style(annot, style, border=False)
    return annot.xref


def add_note(page: pymupdf.Page, point: Point, text: str, style: AnnotationStyle) -> int:
    """Nota adhesiva (icono de comentario) con ``text`` en ``point``."""
    annot = page.add_text_annot(pymupdf.Point(point) * page.derotation_matrix, text, icon="Comment")
    _apply_style(annot, style, border=False)
    return annot.xref


def add_free_text(
    page: pymupdf.Page, rect: pymupdf.Rect, text: str, style: AnnotationStyle, fontsize: float = DEFAULT_FONT_SIZE
) -> int:
    """
    Texto escrito sobre la pagina, derecho aunque la pagina este girada. El
    cuadro se ajusta al texto: si ``rect`` es angosto (un clic) toma el ancho
    del texto; si se dibujo, conserva su ancho y crece hacia abajo si hace falta.
    """
    if not text.strip():
        raise InvalidInputError("Escriba el texto que desea agregar.")
    rect = fit_text_rect(page, pymupdf.Rect(rect), text, fontsize, keep_width=pymupdf.Rect(rect).width >= 40)
    annot = page.add_freetext_annot(
        _to_pdf(page, rect),
        text,
        fontsize=fontsize,
        fontname="helv",
        text_color=style.color,
        rotate=page.rotation,
    )
    if style.opacity < 1:
        annot.set_opacity(style.opacity)
        annot.update(text_color=style.color)
    return annot.xref


def add_shape(page: pymupdf.Page, shape: str, rect: pymupdf.Rect, style: AnnotationStyle) -> int:
    """Rectangulo (``"rect"``) o elipse (``"ellipse"``) sin relleno."""
    adders = {"rect": page.add_rect_annot, "ellipse": page.add_circle_annot}
    if shape not in adders:
        raise ValueError(f"Forma no valida: {shape}")
    annot = adders[shape](_to_pdf(page, rect))
    _apply_style(annot, style)
    return annot.xref


def add_line(page: pymupdf.Page, start: Point, end: Point, style: AnnotationStyle, arrow: bool = False) -> int:
    derotate = page.derotation_matrix
    annot = page.add_line_annot(pymupdf.Point(start) * derotate, pymupdf.Point(end) * derotate)
    if arrow:
        annot.set_line_ends(pymupdf.PDF_ANNOT_LE_NONE, pymupdf.PDF_ANNOT_LE_OPEN_ARROW)
    _apply_style(annot, style)
    return annot.xref


def add_ink(page: pymupdf.Page, strokes: Iterable[Sequence[Point]], style: AnnotationStyle) -> int:
    """Dibujo a mano alzada: uno o mas trazos de puntos."""
    derotate = page.derotation_matrix
    paths = [[tuple(pymupdf.Point(point) * derotate) for point in stroke] for stroke in strokes]
    paths = [path for path in paths if len(path) >= 2]
    if not paths:
        raise InvalidInputError("El trazo es demasiado corto.")
    annot = page.add_ink_annot(paths)
    _apply_style(annot, style)
    return annot.xref


# * Editar --------------------------------------------------------------------


def move(page: pymupdf.Page, xref: int, dx: float, dy: float) -> int:
    """
    Desplaza la anotacion ``dx``, ``dy`` puntos (en la pagina visible).
    Devuelve su xref, que cambia si hubo que recrearla (lineas y dibujos).
    """
    annot = find(page, xref)
    kind = annot.type[1]
    origin = pymupdf.Point(0, 0) * page.derotation_matrix
    delta = pymupdf.Point(dx, dy) * page.derotation_matrix - origin
    if kind in RECT_KINDS:
        rect = annot.rect + (delta.x, delta.y, delta.x, delta.y)
        if kind in BORDERED_KINDS:
            half = (annot.border.get("width") or 0) / 2
            rect = rect + (half, half, -half, -half)
        annot.set_rect(rect)
        return xref
    if kind in RECREATE_KINDS:
        return _recreate_moved(page, annot, delta)
    raise InvalidInputError("Este tipo de anotacion no se puede mover (las marcas de texto siguen al texto).")


def delete(page: pymupdf.Page, xref: int) -> None:
    page.delete_annot(find(page, xref))


def set_color(page: pymupdf.Page, xref: int, color: Color) -> None:
    annot = find(page, xref)
    if annot.type[1] == "FreeText":
        annot.update(text_color=color)
    else:
        annot.set_colors(stroke=color)
        annot.update()


def set_text(page: pymupdf.Page, xref: int, text: str) -> None:
    annot = find(page, xref)
    if annot.type[1] == "FreeText" and not text.strip():
        raise InvalidInputError("El texto no puede quedar vacio; elimine la anotacion si ya no la necesita.")
    color = _free_text_color(annot)
    annot.set_info(content=text)
    if annot.type[1] == "FreeText":
        _refit(page, annot, text, font_size(annot) or DEFAULT_FONT_SIZE)
        annot.update(text_color=color)  # vuelve a dibujar el texto con su color


def set_font_size(page: pymupdf.Page, xref: int, size: float) -> None:
    """Cambia el tamano de letra de un texto libre; el cuadro se ajusta al nuevo tamano."""
    annot = find(page, xref)
    if annot.type[1] != "FreeText":
        raise InvalidInputError("Solo los cuadros de texto tienen tamano de letra.")
    if not 4 <= size <= 200:
        raise InvalidInputError("El tamano de letra debe estar entre 4 y 200 puntos.")
    color = _free_text_color(annot)
    _refit(page, annot, annot.info.get("content") or "", size)
    annot.update(fontsize=size, text_color=color)


def font_size(annot: pymupdf.Annot) -> float | None:
    """Tamano de letra de un texto libre (de su cadena /DA: ``/Helv 12 Tf``)."""
    appearance = annot.parent.parent.xref_get_key(annot.xref, "DA")[1]
    match = re.search(r"([\d.]+)\s+Tf", appearance)
    return float(match.group(1)) if match else None


def text_lines(text: str, fontsize: float, width: float) -> list[str]:
    """Lineas en que se parte ``text`` dentro de ``width`` puntos (como lo dibuja MuPDF)."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for word in paragraph.split(" "):
            candidate = f"{current} {word}" if current else word
            if current and pymupdf.get_text_length(candidate, "helv", fontsize) > width:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return lines


def fit_text_rect(
    page: pymupdf.Page, rect: pymupdf.Rect, text: str, fontsize: float, keep_width: bool = True
) -> pymupdf.Rect:
    """
    Cuadro (visible) para ``text``: conserva la esquina superior izquierda y,
    si ``keep_width``, el ancho; el alto es el que necesitan las lineas.
    """
    bounds = page.rect
    if keep_width:
        width = rect.width
    else:
        longest = max(pymupdf.get_text_length(line, "helv", fontsize) for line in text.split("\n"))
        width = min(longest + 2 * TEXT_PADDING + 2, MAX_AUTO_WIDTH)
    width = min(width, bounds.width - 4)
    lines = text_lines(text, fontsize, width - 2 * TEXT_PADDING)
    height = len(lines) * fontsize * LINE_HEIGHT + fontsize * 0.4 + 2
    x0 = max(2.0, min(rect.x0, bounds.width - width - 2))
    y0 = max(2.0, min(rect.y0, bounds.height - height - 2))
    return pymupdf.Rect(x0, y0, x0 + width, y0 + max(height, 12))


def _refit(page: pymupdf.Page, annot: pymupdf.Annot, text: str, size: float) -> None:
    """Ajusta el alto del cuadro de texto a ``text`` con letra ``size`` (conserva el ancho)."""
    visible = annot.rect * page.rotation_matrix
    fitted = fit_text_rect(page, visible, text or " ", size)
    annot.set_rect((fitted * page.derotation_matrix).normalize())


# * Utilidades ----------------------------------------------------------------


def _to_pdf(page: pymupdf.Page, rect: pymupdf.Rect) -> pymupdf.Rect:
    result = (pymupdf.Rect(rect) * page.derotation_matrix).normalize()
    if result.width < 4 or result.height < 4:
        raise InvalidInputError("El area es demasiado pequena: arrastre para dibujarla.")
    return result


def _apply_style(annot: pymupdf.Annot, style: AnnotationStyle, border: bool = True) -> None:
    annot.set_colors(stroke=style.color)
    if border:
        annot.set_border(width=style.width)
    if style.opacity < 1:
        annot.set_opacity(style.opacity)
    annot.update()


def _free_text_color(annot: pymupdf.Annot) -> Color | None:
    """Color del texto de un FreeText (esta en su cadena /DA, no en /C)."""
    if annot.type[1] != "FreeText":
        return None
    appearance = annot.parent.parent.xref_get_key(annot.xref, "DA")[1]
    numbers = appearance.split(" rg")[0].split()[-3:] if " rg" in appearance else []
    try:
        if len(numbers) != 3:
            return None
        red, green, blue = (float(value) for value in numbers)
        return red, green, blue
    except ValueError:
        return None


def _recreate_moved(page: pymupdf.Page, annot: pymupdf.Annot, delta: pymupdf.Point) -> int:
    """Notas, lineas y dibujos: se recrean desplazados con las mismas propiedades."""
    kind = annot.type[1]
    stroke = annot.colors.get("stroke") or (1.0, 0.0, 0.0)
    width = annot.border.get("width") or 1.0
    opacity = annot.opacity if annot.opacity is not None and annot.opacity >= 0 else 1.0
    content = annot.info.get("content") or ""
    vertices = annot.vertices
    line_ends = annot.line_ends
    # Punto visible de la nota: su esquina superior izquierda tal como se ve.
    note_point = pymupdf.Rect(annot.rect * page.rotation_matrix).tl * page.derotation_matrix
    page.delete_annot(annot)
    if kind == "Text":
        new = page.add_text_annot(note_point + delta, content, icon="Comment")
        new.set_colors(stroke=tuple(stroke[:3]))
        if opacity < 1:
            new.set_opacity(opacity)
        new.update()
        return new.xref
    if kind == "Line":
        start, end = (pymupdf.Point(vertex) + delta for vertex in vertices[:2])
        new = page.add_line_annot(start, end)
        if line_ends:
            new.set_line_ends(*line_ends)
    else:
        new = page.add_ink_annot(
            [[tuple(pymupdf.Point(point) + delta) for point in stroke_points] for stroke_points in vertices]
        )
    new.set_colors(stroke=tuple(stroke[:3]))
    new.set_border(width=width)
    if opacity < 1:
        new.set_opacity(opacity)
    if content:
        new.set_info(content=content)
    new.update()
    return new.xref
