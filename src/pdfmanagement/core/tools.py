"""
Herramientas sobre archivos: comprimir, dividir, numerar paginas y marca de agua.

Como el resto del nucleo: reciben rutas, nunca modifican el original, escriben
el resultado de forma atomica y conservan la contrasena (AES-256) si el
documento estaba protegido. Las coordenadas son las de la pagina tal como se
ve, asi funcionan igual en paginas giradas.
"""

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from PIL import Image

from ..i18n import tr
from .documents import open_document
from .editing.content import helvetica_can_write
from .errors import InvalidInputError
from .files import PDF_EXTENSIONS, atomic_output, prepare_output, require_file
from .pages import parse_page_selection

Color = tuple[float, float, float]

# Nivel -> (dpi a partir del cual se reducen imagenes, dpi final, calidad JPEG); None = sin tocar imagenes.
COMPRESSION_LEVELS: dict[str, tuple[int, int, int] | None] = {
    "baja": None,
    "media": (200, 150, 80),
    "alta": (120, 96, 60),
}
SPLIT_MODES = ("rangos", "cada", "marcadores")
POSITIONS = ("arriba-izquierda", "arriba-centro", "arriba-derecha", "abajo-izquierda", "abajo-centro", "abajo-derecha")
NUMBER_MARGIN = 28  # distancia al borde de la pagina, en puntos
# Letra para textos que Helvetica no puede escribir (cirilico, p. ej. "Страница 1 из 4").
UNICODE_FONT = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arial.ttf"


@dataclass(frozen=True)
class TextFont:
    """Letra con la que se escribe un texto: Helvetica si alcanza, si no Arial (Unicode)."""

    name: str
    file: str | None = None

    @classmethod
    def for_text(cls, text: str) -> "TextFont":
        if helvetica_can_write(text) or not UNICODE_FONT.exists():
            return cls("helv")
        return cls("arial", str(UNICODE_FONT))

    def length(self, text: str, fontsize: float) -> float:
        if self.file is None:
            return pymupdf.get_text_length(text, self.name, fontsize)
        return pymupdf.Font(fontfile=self.file).text_length(text, fontsize)


@dataclass(frozen=True)
class CompressionResult:
    path: Path
    size_before: int
    size_after: int

    @property
    def saved_ratio(self) -> float:
        """Fraccion ahorrada (0,25 = 25 % mas liviano)."""
        return 1 - self.size_after / self.size_before if self.size_before else 0.0


# * Utilidades ------------------------------------------------------------------


def _open(path: Path, password: str | None) -> pymupdf.Document:
    return open_document(path, password)


def _save(document: pymupdf.Document, output: Path, password: str | None, **options) -> Path:
    """Guarda de forma atomica; con ``password`` el resultado queda cifrado con la misma clave."""
    if password:
        options.update(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password)
    with atomic_output(output) as temp_path:
        document.save(temp_path, garbage=options.pop("garbage", 3), deflate=True, **options)
    return output


def _pages(document: pymupdf.Document, selection: str | None) -> list[int]:
    return list(range(document.page_count)) if not selection else parse_page_selection(selection, document.page_count)


# * Comprimir -------------------------------------------------------------------


def compress_pdf(
    input_file: str | Path, output_file: str | Path, level: str = "media", *, password: str | None = None
) -> CompressionResult:
    """
    Reduce el tamano: limpia objetos sin uso y comprime flujos; en ``media`` y
    ``alta`` ademas reduce la resolucion de las imagenes grandes y subconjunta
    las fuentes. Si el resultado no es mas liviano, se guarda una copia limpia.
    """
    if level not in COMPRESSION_LEVELS:
        raise InvalidInputError(tr("Nivel de compresión no válido: {level}", level=level))
    source = require_file(input_file, PDF_EXTENSIONS)
    output = prepare_output(output_file, source)
    document = _open(source, password)
    try:
        images = COMPRESSION_LEVELS[level]
        if images is not None:
            threshold, target, quality = images
            document.rewrite_images(dpi_threshold=threshold, dpi_target=target, quality=quality)
            try:
                document.subset_fonts()
            except (RuntimeError, ValueError):
                pass  # algunas fuentes no se pueden subconjuntar: se dejan como estan
        _save(document, output, password, garbage=4, clean=True, deflate_images=True, deflate_fonts=True)
    finally:
        document.close()
    before = source.stat().st_size
    if output.stat().st_size >= before:
        # No se pudo reducir (p. ej. imagenes ya comprimidas): mejor una copia que un archivo mas pesado.
        with atomic_output(output) as temp_path:
            shutil.copyfile(source, temp_path)
    return CompressionResult(output, before, output.stat().st_size)


# * Dividir ---------------------------------------------------------------------


def split_pdf(
    input_file: str | Path,
    output_dir: str | Path,
    mode: str,
    value: str | int = "",
    *,
    password: str | None = None,
) -> list[Path]:
    """
    Divide en varios archivos dentro de ``output_dir``:

    - ``rangos``: ``value`` = grupos separados por ``;`` (``"1-3; 4-6; 7-"``).
    - ``cada``: ``value`` = paginas por archivo.
    - ``marcadores``: un archivo por marcador de primer nivel.
    """
    source = require_file(input_file, PDF_EXTENSIONS)
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    document = _open(source, password)
    try:
        groups = _split_groups(document, mode, value)
        if not groups:
            raise InvalidInputError(tr("No hay páginas para dividir con esa opción."))
        written = []
        width = len(str(len(groups)))
        for index, (name, pages) in enumerate(groups, start=1):
            part = pymupdf.open()
            for page in pages:
                part.insert_pdf(document, from_page=page, to_page=page)
            label = _safe_name(name) if name else f"{tr('parte')}{index:0{width}d}"
            output = prepare_output(folder / f"{source.stem}_{label}.pdf", source)
            written.append(_save(part, output, password))
            part.close()
        return written
    finally:
        document.close()


def _split_groups(document: pymupdf.Document, mode: str, value: str | int) -> list[tuple[str, list[int]]]:
    total = document.page_count
    if mode == "rangos":
        chunks = [chunk.strip() for chunk in str(value).split(";") if chunk.strip()]
        if not chunks:
            raise InvalidInputError(tr("Indique los rangos separados por punto y coma, por ejemplo 1-3; 4-6."))
        return [("", parse_page_selection(chunk, total)) for chunk in chunks]
    if mode == "cada":
        try:
            size = int(value)
        except (TypeError, ValueError):
            size = 0
        if size < 1:
            raise InvalidInputError(tr("Indique cuántas páginas debe tener cada archivo (1 o más)."))
        return [("", list(range(start, min(start + size, total)))) for start in range(0, total, size)]
    if mode == "marcadores":
        tops = [
            (title, page - 1) for level, title, page, *_ in document.get_toc(simple=True) if level == 1 and page >= 1
        ]
        if not tops:
            raise InvalidInputError(tr("El documento no tiene marcadores para dividir."))
        groups = []
        for index, (title, start) in enumerate(tops):
            end = tops[index + 1][1] if index + 1 < len(tops) else total
            if end > start:
                groups.append((title, list(range(start, end))))
        return groups
    raise InvalidInputError(tr("Modo de división no válido: {mode}", mode=mode))


def _safe_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip().strip(".")
    return re.sub(r"\s+", "_", cleaned)[:60] or "parte"


# * Numerar paginas ---------------------------------------------------------------


def add_page_numbers(
    input_file: str | Path,
    output_file: str | Path,
    *,
    template: str | None = None,
    position: str = "abajo-centro",
    start: int = 1,
    fontsize: float = 10,
    color: Color = (0.2, 0.2, 0.2),
    pages: str | None = None,
    password: str | None = None,
) -> Path:
    """
    Escribe el numero de pagina en cada pagina (o en ``pages``). ``template``
    admite ``{n}`` (numero) y ``{total}``; por defecto "Página {n} de {total}".
    El numero empieza en ``start`` y cuenta solo las paginas numeradas.
    """
    if position not in POSITIONS:
        raise InvalidInputError(tr("Posición no válida: {position}", position=position))
    template = template or tr("Página {n} de {total}")
    source = require_file(input_file, PDF_EXTENSIONS)
    output = prepare_output(output_file, source)
    document = _open(source, password)
    try:
        selected = _pages(document, pages)
        total = len(selected) + start - 1
        for offset, index in enumerate(selected):
            try:
                text = template.format(n=start + offset, total=total)
            except (KeyError, IndexError, ValueError) as error:
                raise InvalidInputError(tr("El formato solo admite {{n}} y {{total}}.")) from error
            _write_at(document[index], text, position, fontsize, color)
        _save(document, output, password)
    finally:
        document.close()
    return output


def _write_at(page: pymupdf.Page, text: str, position: str, fontsize: float, color: Color) -> None:
    """Escribe ``text`` en una esquina o centro del borde de la pagina tal como se ve."""
    width, height = page.rect.width, page.rect.height
    font = TextFont.for_text(text)
    text_width = font.length(text, fontsize)
    vertical, horizontal = position.split("-")
    x = {
        "izquierda": NUMBER_MARGIN,
        "centro": (width - text_width) / 2,
        "derecha": width - NUMBER_MARGIN - text_width,
    }[horizontal]
    y = NUMBER_MARGIN + fontsize if vertical == "arriba" else height - NUMBER_MARGIN
    point = pymupdf.Point(x, y) * page.derotation_matrix
    page.insert_text(
        point, text, fontsize=fontsize, fontname=font.name, fontfile=font.file, color=color, rotate=page.rotation
    )


# * Marca de agua -----------------------------------------------------------------


def add_watermark(
    input_file: str | Path,
    output_file: str | Path,
    text: str,
    *,
    fontsize: float = 60,
    opacity: float = 0.15,
    angle: float = 45,
    color: Color = (0.5, 0.5, 0.5),
    pages: str | None = None,
    behind: bool = False,
    password: str | None = None,
) -> Path:
    """Texto grande, semitransparente y girado en el centro de cada pagina."""
    if not text.strip():
        raise InvalidInputError(tr("Escriba el texto de la marca de agua."))
    if not 0.02 <= opacity <= 1:
        raise InvalidInputError(tr("La opacidad debe estar entre 2 % y 100 %."))
    source = require_file(input_file, PDF_EXTENSIONS)
    output = prepare_output(output_file, source)
    document = _open(source, password)
    try:
        for index in _pages(document, pages):
            _stamp_watermark(document[index], text.strip(), fontsize, opacity, angle, color, behind)
        _save(document, output, password)
    finally:
        document.close()
    return output


def watermark_preview(
    input_file: str | Path,
    text: str,
    *,
    height: int = 300,
    fontsize: float = 60,
    opacity: float = 0.15,
    angle: float = 45,
    color: Color = (0.5, 0.5, 0.5),
    behind: bool = False,
    password: str | None = None,
) -> Image.Image:
    """
    Primera pagina con la marca de agua tal como quedara, como imagen de
    ``height`` pixeles de alto. No guarda nada: la marca se dibuja en memoria.
    """
    source = require_file(input_file, PDF_EXTENSIONS)
    document = _open(source, password)
    try:
        if not document.page_count:
            raise InvalidInputError(tr("El PDF no tiene páginas."))
        page = document[0]
        if text.strip():
            _stamp_watermark(page, text.strip(), fontsize, opacity, angle, color, behind)
        zoom = height / page.rect.height
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
    finally:
        document.close()


def _stamp_watermark(
    page: pymupdf.Page, text: str, fontsize: float, opacity: float, angle: float, color: Color, behind: bool
) -> None:
    width, height = page.rect.width, page.rect.height
    # No mas ancha que la diagonal de la pagina: se reduce la letra si hace falta.
    diagonal = (width**2 + height**2) ** 0.5 * 0.8
    font = TextFont.for_text(text)
    text_width = font.length(text, fontsize)
    if text_width > diagonal:
        fontsize *= diagonal / text_width
        text_width = diagonal
    center = pymupdf.Point(width / 2, height / 2)
    start = pymupdf.Point(center.x - text_width / 2, center.y + fontsize / 3)
    derotate = page.derotation_matrix
    # Giro alrededor del centro de la pagina visible; se aplica en coordenadas del PDF.
    page.insert_text(
        start * derotate,
        text,
        fontsize=fontsize,
        fontname=font.name,
        fontfile=font.file,
        color=color,
        fill_opacity=opacity,
        stroke_opacity=opacity,
        rotate=page.rotation,
        morph=(center * derotate, pymupdf.Matrix(-angle)),
        overlay=not behind,
    )
