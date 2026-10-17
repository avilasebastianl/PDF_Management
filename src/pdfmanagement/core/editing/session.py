"""
Sesion de documento: un PDF abierto en memoria para verlo y editarlo.

Concentra el estado que comparten el visor y las futuras herramientas de
edicion: el ``pymupdf.Document``, su historial de cambios, la contrasena con
que se abrio y el guardado. Siempre se guarda en un archivo nuevo ("Guardar
como"); el original nunca se modifica.
"""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pymupdf

from ...i18n import tr, trn
from ..documents import open_document
from ..errors import InvalidInputError
from ..files import PDF_EXTENSIONS, atomic_output, prepare_output, require_file
from . import annotations as annots
from . import content, engine
from . import pages as page_ops
from .annotations import AnnotationInfo, AnnotationStyle
from .changes import CONTENT, SAVED, STRUCTURE, ChangeNotifier, DocumentChange
from .history import History
from .text import page_words

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DocumentProperties:
    """Datos del documento para el dialogo de propiedades."""

    path: Path
    page_count: int
    size_bytes: int
    pdf_version: str
    encrypted: bool
    has_signatures: bool
    title: str
    author: str
    subject: str
    keywords: str
    creator: str
    producer: str
    created: str
    modified: str


class DocumentSession:
    """Documento abierto, con historial y guardado seguro."""

    def __init__(
        self,
        document: pymupdf.Document,
        path: Path,
        password: str | None = None,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self.document = document
        self.path = path
        self.password = password
        # No usar ``needs_pass`` aqui: MuPDF vuelve a autenticar con contrasena
        # vacia y reemplaza la clave buena; el documento se leeria en blanco.
        self.encrypted = password is not None or engine.was_encrypted(document)
        engine.prepare_font_cache(document)  # antes del historial (ver engine, punto 5)
        self.history = History(document, on_change=on_change)
        self.changes = ChangeNotifier()  # avisa de cada cambio a quien muestra el documento
        self._words: dict[int, list[tuple]] = {}

    @classmethod
    def open(
        cls, pdf_file: str | Path, password: str | None = None, on_change: Callable[[], None] | None = None
    ) -> "DocumentSession":
        """
        Abre un PDF. Lanza ``PasswordRequiredError`` / ``WrongPasswordError``
        si esta protegido y la contrasena falta o no es correcta.
        """
        path = require_file(pdf_file, PDF_EXTENSIONS)
        document = open_document(path, password)
        if document.page_count == 0:
            document.close()
            raise InvalidInputError(tr("'{name}' no tiene páginas.", name=path.name))
        session = cls(document, path, password, on_change)
        logger.info("Documento abierto: %s (%d paginas)", path.name, document.page_count)
        return session

    # * Consultas -----------------------------------------------------------

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def page_count(self) -> int:
        return self.document.page_count

    @property
    def modified(self) -> bool:
        return self.history.modified

    def page_rect(self, index: int) -> pymupdf.Rect:
        """Tamano visible de la pagina (con su rotacion) en puntos."""
        return self.document[index].rect

    def page_sizes(self) -> list[tuple[float, float]]:
        """Ancho y alto visibles de todas las paginas (rapido: ~15 ms por 300 paginas)."""
        return [(page.rect.width, page.rect.height) for page in self.document]

    def words(self, index: int) -> list[tuple]:
        """
        Palabras de la pagina en orden de lectura: ``(x0, y0, x1, y1, texto,
        bloque, linea, palabra)``. Se guardan en cache por pagina.
        """
        if index not in self._words:
            self._words[index] = page_words(self.document[index], sort=True)
        return self._words[index]

    def invalidate(self, pages: list[int] | None = None) -> None:
        """Descarta la cache de texto tras una edicion (todas o algunas paginas)."""
        if pages is None:
            self._words.clear()
        for index in pages or []:
            self._words.pop(index, None)

    def has_signatures(self) -> bool:
        """El PDF contiene firmas digitales (editarlo las invalidaria)."""
        try:
            return self.document.get_sigflags() > 0
        except (RuntimeError, ValueError):
            return False

    def table_of_contents(self) -> list[tuple[int, str, int]]:
        """Marcadores: ``(nivel, titulo, pagina desde 1)``."""
        return [(int(level), str(title), int(page)) for level, title, page, *_ in self.document.get_toc(simple=True)]

    def properties(self) -> DocumentProperties:
        meta = self.document.metadata or {}
        return DocumentProperties(
            path=self.path,
            page_count=self.page_count,
            size_bytes=self.path.stat().st_size if self.path.exists() else 0,
            pdf_version=meta.get("format", "") or "",
            encrypted=self.encrypted,
            has_signatures=self.has_signatures(),
            title=meta.get("title", "") or "",
            author=meta.get("author", "") or "",
            subject=meta.get("subject", "") or "",
            keywords=meta.get("keywords", "") or "",
            creator=meta.get("creator", "") or "",
            producer=meta.get("producer", "") or "",
            created=_pdf_date(meta.get("creationDate", "")),
            modified=_pdf_date(meta.get("modDate", "")),
        )

    # * Edicion de paginas ---------------------------------------------------

    def rotate(self, pages: Iterable[int], angle: int) -> str:
        """Gira paginas (indices desde 0) ``angle`` grados; positivo = horario."""
        pages = self._valid_pages(pages)
        # Una página se nombra por su número y varias por su cantidad.
        if angle > 0:
            label = (
                tr("Rotar página {page} a la derecha", page=pages[0] + 1)
                if len(pages) == 1
                else trn("Rotar {count} página a la derecha", "Rotar {count} páginas a la derecha", len(pages))
            )
        else:
            label = (
                tr("Rotar página {page} a la izquierda", page=pages[0] + 1)
                if len(pages) == 1
                else trn("Rotar {count} página a la izquierda", "Rotar {count} páginas a la izquierda", len(pages))
            )
        return self._edit(label, page_ops.rotate_pages, pages, angle)

    def delete(self, pages: Iterable[int]) -> str:
        pages = self._valid_pages(pages)
        if len(pages) >= self.page_count:
            raise InvalidInputError(
                tr("No se pueden eliminar todas las páginas: el documento debe conservar al menos una.")
            )
        label = (
            tr("Eliminar página {page}", page=pages[0] + 1)
            if len(pages) == 1
            else trn("Eliminar {count} página", "Eliminar {count} páginas", len(pages))
        )
        return self._edit(label, page_ops.delete_pages, pages)

    def move(self, pages: Iterable[int], target: int) -> list[int]:
        """
        Mueve ``pages`` delante de la pagina que hoy esta en ``target``
        (``page_count`` = al final). Devuelve los nuevos indices de las
        paginas movidas; si el orden no cambia no registra nada.
        """
        pages = self._valid_pages(pages)
        target = max(0, min(target, self.page_count))
        rest = [index for index in range(self.page_count) if index not in pages]
        position = sum(1 for index in rest if index < target)
        if pages == list(range(position, position + len(pages))):
            return pages  # ya estan ahi
        result: list[int] = []
        label = (
            tr("Mover página {page}", page=pages[0] + 1)
            if len(pages) == 1
            else trn("Mover {count} página", "Mover {count} páginas", len(pages))
        )
        self._edit(label, lambda document: result.extend(page_ops.move_pages(document, pages, target)))
        return result

    def insert_pdf(self, source_file: str | Path, at: int, password: str | None = None) -> int:
        """
        Inserta todas las paginas de otro PDF antes de ``at``. Lanza
        ``PasswordRequiredError`` / ``WrongPasswordError`` si esta protegido.
        Devuelve la cantidad de paginas insertadas.
        """
        path = require_file(source_file, PDF_EXTENSIONS)
        source = open_document(path, password)
        try:
            if source.page_count == 0:
                raise InvalidInputError(tr("'{name}' no tiene páginas.", name=path.name))
            # Copia en memoria sin cifrado: se modifica al copiar las anotaciones.
            copy = pymupdf.open("pdf", source.tobytes())
        finally:
            source.close()
        at = max(0, min(at, self.page_count))
        try:
            count = copy.page_count
            label = trn(
                "Insertar {count} página de {name}", "Insertar {count} páginas de {name}", count, name=path.name
            )
            self._edit(label, page_ops.insert_document, copy, at)
        finally:
            copy.close()
        return count

    def insert_blank(self, at: int, size: tuple[float, float] | None = None) -> str:
        """Inserta una pagina en blanco antes de ``at`` (por defecto, del tamano de la vecina)."""
        at = max(0, min(at, self.page_count))
        if size is None:
            neighbor = self.document[min(at, self.page_count - 1)]
            size = (neighbor.mediabox.width, neighbor.mediabox.height)
        return self._edit(tr("Insertar página en blanco"), page_ops.insert_blank_page, at, *size)

    # * Anotaciones -----------------------------------------------------------
    # Coordenadas de la pagina tal como se ve; cada metodo es un paso deshacible.

    def annotations(self, page: int | None = None) -> list[AnnotationInfo]:
        """Anotaciones de una pagina (indice desde 0) o de todo el documento."""
        pages = range(self.page_count) if page is None else [page]
        result: list[AnnotationInfo] = []
        for index in pages:
            current = self.document[index]
            result.extend(annots.list_annotations(current, index))
        return result

    def add_markup(self, page: int, kind: str, rects, style: AnnotationStyle) -> int:
        number = page + 1
        if kind == "highlight":
            label = tr("Resaltar texto (página {page})", page=number)
        elif kind == "underline":
            label = tr("Subrayar texto (página {page})", page=number)
        elif kind == "strikeout":
            label = tr("Tachar texto (página {page})", page=number)
        else:
            label = tr("Marcar texto (página {page})", page=number)
        return self._annotate(label, page, annots.add_markup, kind, rects, style)

    def add_note(self, page: int, point, text: str, style: AnnotationStyle) -> int:
        label = tr("Agregar nota (página {page})", page=page + 1)
        return self._annotate(label, page, annots.add_note, point, text, style)

    def add_free_text(
        self, page: int, rect, text: str, style: AnnotationStyle, fontsize: float = annots.DEFAULT_FONT_SIZE
    ) -> int:
        label = tr("Agregar texto (página {page})", page=page + 1)
        return self._annotate(label, page, annots.add_free_text, rect, text, style, fontsize)

    def add_shape(self, page: int, shape: str, rect, style: AnnotationStyle) -> int:
        if shape == "rect":
            label = tr("Agregar rectángulo (página {page})", page=page + 1)
        else:
            label = tr("Agregar elipse (página {page})", page=page + 1)
        return self._annotate(label, page, annots.add_shape, shape, rect, style)

    def add_line(self, page: int, start, end, style: AnnotationStyle, arrow: bool = False) -> int:
        if arrow:
            label = tr("Agregar flecha (página {page})", page=page + 1)
        else:
            label = tr("Agregar línea (página {page})", page=page + 1)
        return self._annotate(label, page, annots.add_line, start, end, style, arrow)

    def add_ink(self, page: int, strokes, style: AnnotationStyle) -> int:
        label = tr("Dibujar a mano (página {page})", page=page + 1)
        return self._annotate(label, page, annots.add_ink, strokes, style)

    def move_annotation(self, page: int, xref: int, dx: float, dy: float) -> int:
        """Devuelve el xref de la anotacion movida (cambia si hubo que recrearla)."""
        label = tr("Mover {annotation}", annotation=self._annotation_label(page, xref))
        return self._annotate(label, page, annots.move, xref, dx, dy)

    def delete_annotation(self, page: int, xref: int) -> None:
        label = tr("Eliminar {annotation}", annotation=self._annotation_label(page, xref))
        self._annotate(label, page, annots.delete, xref)

    def set_annotation_color(self, page: int, xref: int, color) -> None:
        label = tr("Cambiar color de {annotation}", annotation=self._annotation_label(page, xref))
        self._annotate(label, page, annots.set_color, xref, color)

    def set_annotation_font_size(self, page: int, xref: int, size: float) -> None:
        self._annotate(tr("Cambiar tamaño de texto"), page, annots.set_font_size, xref, size)

    def set_annotation_text(self, page: int, xref: int, text: str) -> None:
        label = tr("Editar texto de {annotation}", annotation=self._annotation_label(page, xref))
        self._annotate(label, page, annots.set_text, xref, text)

    # * Contenido de la pagina (fase 4) -----------------------------------------
    # Cambia el contenido mismo: lo tapado o reemplazado desaparece de verdad.

    def replace_text(self, page: int, rects, new_text: str) -> None:
        self._annotate(
            tr("Reemplazar texto (página {page})", page=page + 1), page, content.replace_text, rects, new_text
        )

    def add_fixed_text(self, page: int, point, text: str, fontsize: float, color) -> None:
        self._annotate(
            tr("Agregar texto fijo (página {page})", page=page + 1),
            page,
            content.add_text,
            point,
            text,
            fontsize,
            color,
        )

    def add_image(self, page: int, rect, image_file) -> None:
        self._annotate(tr("Agregar imagen (página {page})", page=page + 1), page, content.add_image, rect, image_file)

    def redact(self, page: int, rect) -> None:
        self._annotate(tr("Tapar contenido (página {page})", page=page + 1), page, content.redact, rect)

    def _annotation_label(self, page: int, xref: int) -> str:
        """Nombre de la anotacion en minusculas, para componer la etiqueta del historial."""
        current = self.document[page]
        kind = annots.find(current, xref).type[1]
        return annots.kind_label(kind, tr("Anotación")).lower()

    def _annotate(self, label: str, page: int, operation: Callable, *args):
        if not 0 <= page < self.page_count:
            raise InvalidInputError(tr("La página no existe."))
        result = None
        steps = self.history.undo_depth
        with self.history.operation(label):
            current = self.document[page]  # debe seguir viva mientras se usa la anotacion
            result = operation(current, *args)
        if self.history.undo_depth != steps:
            self.invalidate([page])  # reemplazar o tapar cambia el texto de la pagina
            logger.info("Anotacion: %s (%s)", label, self.name)
            self.changes.emit(DocumentChange(CONTENT, label, frozenset({page})))
        return result

    def undo(self) -> str | None:
        label = self.history.undo()
        if label is not None:
            self.invalidate()
            self.changes.emit(DocumentChange(STRUCTURE, label))
        return label

    def redo(self) -> str | None:
        label = self.history.redo()
        if label is not None:
            self.invalidate()
            self.changes.emit(DocumentChange(STRUCTURE, label))
        return label

    def _edit(self, label: str, operation: Callable, *args) -> str:
        steps = self.history.undo_depth
        with self.history.operation(label):
            operation(self.document, *args)
        if self.history.undo_depth != steps:
            self.invalidate()
            logger.info("Edicion: %s (%s)", label, self.name)
            self.changes.emit(DocumentChange(STRUCTURE, label))
        return label

    def _valid_pages(self, pages: Iterable[int]) -> list[int]:
        selected = sorted(set(pages))
        if not selected:
            raise InvalidInputError(tr("Seleccione al menos una página."))
        if selected[0] < 0 or selected[-1] >= self.page_count:
            raise InvalidInputError(tr("La selección incluye páginas que no existen."))
        return selected

    # * Guardado ------------------------------------------------------------

    def save_as(self, output_file: str | Path, *, keep_encryption: bool = True) -> Path:
        """
        Guarda una copia optimizada en un archivo nuevo, sin tocar el original.

        Se guarda desde una copia en memoria: compactar el documento vivo
        romperia el historial de deshacer. Si el original estaba protegido y
        ``keep_encryption`` es verdadero, la copia conserva la contrasena
        (AES-256).
        """
        output = prepare_output(output_file, self.path)
        copy = pymupdf.open("pdf", self.document.tobytes())
        options: dict = {"garbage": 3, "deflate": True}
        if keep_encryption and self.password:
            options.update(
                encryption=pymupdf.PDF_ENCRYPT_AES_256,
                user_pw=self.password,
                owner_pw=self.password,
            )
        try:
            with atomic_output(output) as temp_path:
                copy.save(temp_path, **options)
        finally:
            copy.close()
        self.history.mark_saved()
        logger.info("Documento guardado como: %s", output)
        self.changes.emit(DocumentChange(SAVED, str(output)))
        return output

    def close(self) -> None:
        self.document.close()


def _pdf_date(value: str) -> str:
    """``D:20261017103000-05'00'`` -> ``17/10/2026 10:30``."""
    digits = value.removeprefix("D:")[:14]
    for pattern in ("%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y%m%d"):
        try:
            return datetime.strptime(digits[: len(datetime.now().strftime(pattern))], pattern).strftime(
                "%d/%m/%Y %H:%M"
            )
        except ValueError:
            continue
    return value or ""
