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

from ..documents import open_document
from ..errors import InvalidInputError
from ..files import PDF_EXTENSIONS, atomic_output, prepare_output, require_file
from . import pages as page_ops
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

    def __init__(self, document: pymupdf.Document, path: Path, password: str | None = None,
                 on_change: Callable[[], None] | None = None) -> None:
        self.document = document
        self.path = path
        self.password = password
        # No usar ``needs_pass`` aqui: MuPDF vuelve a autenticar con contrasena
        # vacia y reemplaza la clave buena; el documento se leeria en blanco.
        self.encrypted = password is not None or bool((document.metadata or {}).get("encryption"))
        self.history = History(document, on_change=on_change)
        self._words: dict[int, list[tuple]] = {}

    @classmethod
    def open(cls, pdf_file: str | Path, password: str | None = None,
             on_change: Callable[[], None] | None = None) -> "DocumentSession":
        """
        Abre un PDF. Lanza ``PasswordRequiredError`` / ``WrongPasswordError``
        si esta protegido y la contrasena falta o no es correcta.
        """
        path = require_file(pdf_file, PDF_EXTENSIONS)
        document = open_document(path, password)
        if document.page_count == 0:
            document.close()
            raise InvalidInputError(f"'{path.name}' no tiene paginas.")
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
        side = "derecha" if angle > 0 else "izquierda"
        return self._edit(f"Rotar {_describe(pages)} a la {side}", page_ops.rotate_pages, pages, angle)

    def delete(self, pages: Iterable[int]) -> str:
        pages = self._valid_pages(pages)
        if len(pages) >= self.page_count:
            raise InvalidInputError("No se pueden eliminar todas las paginas: el documento debe conservar al menos una.")
        return self._edit(f"Eliminar {_describe(pages)}", page_ops.delete_pages, pages)

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
        self._edit(f"Mover {_describe(pages)}",
                   lambda document: result.extend(page_ops.move_pages(document, pages, target)))
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
                raise InvalidInputError(f"'{path.name}' no tiene paginas.")
            # Copia en memoria sin cifrado: se modifica al copiar las anotaciones.
            copy = pymupdf.open("pdf", source.tobytes())
        finally:
            source.close()
        at = max(0, min(at, self.page_count))
        try:
            count = copy.page_count
            self._edit(f"Insertar {_plural(count, 'pagina')} de {path.name}", page_ops.insert_document, copy, at)
        finally:
            copy.close()
        return count

    def insert_blank(self, at: int, size: tuple[float, float] | None = None) -> str:
        """Inserta una pagina en blanco antes de ``at`` (por defecto, del tamano de la vecina)."""
        at = max(0, min(at, self.page_count))
        if size is None:
            neighbor = self.document[min(at, self.page_count - 1)]
            size = (neighbor.mediabox.width, neighbor.mediabox.height)
        return self._edit("Insertar pagina en blanco", page_ops.insert_blank_page, at, *size)

    def undo(self) -> str | None:
        label = self.history.undo()
        self.invalidate()
        return label

    def redo(self) -> str | None:
        label = self.history.redo()
        self.invalidate()
        return label

    def _edit(self, label: str, operation: Callable, *args) -> str:
        with self.history.operation(label):
            operation(self.document, *args)
        self.invalidate()
        logger.info("Edicion: %s (%s)", label, self.name)
        return label

    def _valid_pages(self, pages: Iterable[int]) -> list[int]:
        selected = sorted(set(pages))
        if not selected:
            raise InvalidInputError("Seleccione al menos una pagina.")
        if selected[0] < 0 or selected[-1] >= self.page_count:
            raise InvalidInputError("La seleccion incluye paginas que no existen.")
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
                encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=self.password, owner_pw=self.password,
            )
        try:
            with atomic_output(output) as temp_path:
                copy.save(temp_path, **options)
        finally:
            copy.close()
        self.history.mark_saved()
        logger.info("Documento guardado como: %s", output)
        return output

    def close(self) -> None:
        self.document.close()


def _plural(count: int, word: str) -> str:
    return f"1 {word}" if count == 1 else f"{count} {word}s"


def _describe(pages: list[int]) -> str:
    """``[2]`` -> "pagina 3"; ``[0, 1]`` -> "2 paginas"."""
    return f"pagina {pages[0] + 1}" if len(pages) == 1 else _plural(len(pages), "pagina")


def _pdf_date(value: str) -> str:
    """``D:20261017103000-05'00'`` -> ``17/10/2026 10:30``."""
    digits = value.removeprefix("D:")[:14]
    for pattern in ("%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y%m%d"):
        try:
            return datetime.strptime(digits[: len(datetime.now().strftime(pattern))], pattern).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            continue
    return value or ""
