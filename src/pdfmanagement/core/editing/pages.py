"""
Operaciones de pagina compatibles con el historial (journal) de MuPDF.

``Document.insert_pdf`` y ``Document.new_page`` de PyMuPDF 1.28 no se pueden
usar con el journal activo: comprueban el estado con ``pdf_undoredo_step``,
que MuPDF rechaza dentro de una operacion ("Can't undo/redo during an
operation"). Por eso insertar paginas usa directamente las primitivas de
MuPDF (``pdf_graft_mapped_page``, ``pdf_add_page``), que si quedan registradas
y se pueden deshacer. Rotar, eliminar y reordenar usan la API normal.

Todas las funciones reciben indices desde 0 y deben llamarse dentro de
``History.operation``.
"""

from collections.abc import Iterable, Sequence

import pymupdf

mupdf = pymupdf.mupdf


def rotate_pages(document: pymupdf.Document, pages: Iterable[int], angle: int) -> None:
    """Gira las paginas ``angle`` grados (multiplo de 90; positivo = horario)."""
    if angle % 90 or angle % 360 == 0:
        raise ValueError(f"Angulo no valido: {angle}")
    for index in pages:
        page = document[index]
        page.set_rotation((page.rotation + angle) % 360)


def delete_pages(document: pymupdf.Document, pages: Iterable[int]) -> None:
    document.delete_pages(sorted(set(pages)))


def move_pages(document: pymupdf.Document, pages: Iterable[int], target: int) -> list[int]:
    """
    Mueve ``pages`` (en su orden actual) para que queden antes de la pagina
    que hoy esta en ``target`` (``page_count`` = al final). Devuelve los nuevos
    indices de las paginas movidas.
    """
    moving = sorted(set(pages))
    count = document.page_count
    rest = [index for index in range(count) if index not in moving]
    position = sum(1 for index in rest if index < target)
    order = rest[:position] + moving + rest[position:]
    if order != list(range(count)):
        document.select(order)
    return list(range(position, position + len(moving)))


def insert_document(document: pymupdf.Document, source: pymupdf.Document, at: int,
                    pages: Sequence[int] | None = None) -> int:
    """
    Inserta las paginas ``pages`` de ``source`` (todas si es ``None``) antes de
    ``at``. Copia contenido, recursos, rotacion y anotaciones; los enlaces a
    otras paginas del documento de origen se descartan (apuntarian a paginas
    que no existen aqui). ``source`` se modifica: debe ser una copia propia.
    Devuelve la cantidad de paginas insertadas.
    """
    selected = list(range(source.page_count)) if pages is None else list(pages)
    target = pymupdf._as_pdf_document(document)  # noqa: SLF001
    origin = pymupdf._as_pdf_document(source)  # noqa: SLF001
    graft_map = mupdf.PdfGraftMap(target)
    for offset, number in enumerate(selected):
        mupdf.pdf_graft_mapped_page(graft_map, at + offset, origin, number)
        _copy_annotations(graft_map, target, origin, number, at + offset)
    document._reset_page_refs()  # noqa: SLF001
    return len(selected)


def insert_blank_page(document: pymupdf.Document, at: int, width: float, height: float) -> None:
    """Inserta una pagina en blanco de ``width`` x ``height`` puntos antes de ``at``."""
    target = pymupdf._as_pdf_document(document)  # noqa: SLF001
    resources = mupdf.pdf_new_dict(target, 1)
    page = mupdf.pdf_add_page(target, mupdf.FzRect(0, 0, width, height), 0, resources, mupdf.FzBuffer(0))
    mupdf.pdf_insert_page(target, at, page)
    document._reset_page_refs()  # noqa: SLF001


def _copy_annotations(graft_map, target, origin, source_number: int, target_number: int) -> None:
    """``pdf_graft_mapped_page`` no copia ``/Annots``: se copian aqui."""
    annotations = mupdf.pdf_dict_get(mupdf.pdf_lookup_page_obj(origin, source_number), mupdf.PDF_ENUM_NAME_Annots)
    if not mupdf.pdf_is_array(annotations):
        return
    new_page = mupdf.pdf_lookup_page_obj(target, target_number)
    copies = mupdf.pdf_new_array(target, mupdf.pdf_array_len(annotations))
    for position in range(mupdf.pdf_array_len(annotations)):
        annotation = mupdf.pdf_array_get(annotations, position)
        subtype = mupdf.pdf_to_name(mupdf.pdf_dict_get(annotation, mupdf.PDF_ENUM_NAME_Subtype))
        if subtype == "Widget":
            continue  # campos de formulario: dependen del /AcroForm del otro documento
        if subtype == "Link":
            action = mupdf.pdf_dict_get(annotation, mupdf.PDF_ENUM_NAME_A)
            if mupdf.pdf_to_name(mupdf.pdf_dict_get(action, mupdf.PDF_ENUM_NAME_S)) != "URI":
                continue  # enlace interno del otro documento
        # /P apunta a la pagina de origen: injertarlo copiaria esa pagina entera.
        mupdf.pdf_dict_del(annotation, mupdf.PDF_ENUM_NAME_P)
        popup = mupdf.pdf_dict_get(annotation, mupdf.PDF_ENUM_NAME_Popup)
        if mupdf.pdf_is_dict(popup):
            mupdf.pdf_dict_del(popup, mupdf.PDF_ENUM_NAME_P)
        copy = mupdf.pdf_graft_mapped_object(graft_map, annotation)
        mupdf.pdf_dict_put(copy, mupdf.PDF_ENUM_NAME_P, new_page)
        popup_copy = mupdf.pdf_dict_get(copy, mupdf.PDF_ENUM_NAME_Popup)
        if mupdf.pdf_is_dict(popup_copy):
            mupdf.pdf_dict_put(popup_copy, mupdf.PDF_ENUM_NAME_P, new_page)
        mupdf.pdf_array_push(copies, copy)
    if mupdf.pdf_array_len(copies):
        mupdf.pdf_dict_put(new_page, mupdf.PDF_ENUM_NAME_Annots, copies)
