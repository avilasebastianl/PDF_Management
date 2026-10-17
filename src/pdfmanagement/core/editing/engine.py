"""
Puente con PyMuPDF: todo lo que depende de su API interna o rodea sus fallos.

El resto del nucleo usa solo la API publica de PyMuPDF y estas funciones. Si
una version nueva cambia algo, aqui (y en ``tests/test_engine.py``, que
verifica cada comportamiento) es donde hay que mirar. Verificado con PyMuPDF
1.28 (``requirements.txt`` fija la version).

Comportamientos de PyMuPDF/MuPDF que se rodean:

1. ``Page.get_text`` / ``search_for`` ponen la rotacion de la pagina a 0
   mientras extraen: con el historial activo falla ("Can't alter an object
   other than in an operation") y ademas devuelve coordenadas sin rotar.
2. ``Document.insert_pdf`` y ``new_page`` consultan el journal de una forma
   que MuPDF rechaza dentro de una operacion: se usan sus primitivas.
3. ``Annot`` y ``Page`` quedan apuntando a otra pagina tras mover, insertar o
   deshacer: hay que invalidar las referencias en cache.
4. MuPDF descarta las operaciones vacias del journal: hay que comparar la
   posicion antes y despues.
5. La cache de fuentes de MuPDF conserva objetos que un deshacer borro.
6. Leer ``needs_pass`` tras autenticar reemplaza la clave buena.
7. ``Page.insert_text`` agrega la fuente con ``insert_font``, que (como en el
   punto 2) no funciona dentro de una operacion si la pagina aun no la tiene.
"""

import logging

import pymupdf

logger = logging.getLogger(__name__)
mupdf = pymupdf.mupdf

TESTED_VERSION = "1.28"


def check_version() -> bool:
    """Avisa en el registro si la version instalada no es la verificada."""
    version = getattr(pymupdf, "__version__", "")
    if not version.startswith(TESTED_VERSION):
        logger.warning(
            "PyMuPDF %s no es la version verificada (%s.x): revise tests/test_engine.py", version, TESTED_VERSION
        )
        return False
    return True


# * 1. Texto en coordenadas visibles --------------------------------------------


def visible_textpage(page: pymupdf.Page, flags: int) -> pymupdf.TextPage:
    """``TextPage`` de la pagina tal como se ve, sin modificar el documento."""
    # Lo mismo que get_textpage pero sin cambiar la rotacion (ver punto 1).
    textpage = pymupdf.TextPage(page._get_textpage(None, flags=flags, matrix=pymupdf.Matrix(1, 1)))  # noqa: SLF001
    textpage.parent = page
    return textpage


# * 2. Insertar paginas dentro del historial ------------------------------------


def graft_pages(document: pymupdf.Document, source: pymupdf.Document, at: int, pages: list[int]) -> None:
    """
    Copia ``pages`` de ``source`` antes de ``at`` (contenido, recursos, rotacion
    y anotaciones; sin enlaces internos ni campos del otro documento).
    ``source`` se modifica: debe ser una copia propia.
    """
    target, origin = _pdf(document), _pdf(source)
    graft_map = mupdf.PdfGraftMap(target)
    for offset, number in enumerate(pages):
        mupdf.pdf_graft_mapped_page(graft_map, at + offset, origin, number)
        _copy_annotations(graft_map, target, origin, number, at + offset)
    reset_page_refs(document)


def add_blank_page(document: pymupdf.Document, at: int, width: float, height: float) -> None:
    target = _pdf(document)
    resources = mupdf.pdf_new_dict(target, 1)
    page = mupdf.pdf_add_page(target, mupdf.FzRect(0, 0, width, height), 0, resources, mupdf.FzBuffer(0))
    mupdf.pdf_insert_page(target, at, page)
    reset_page_refs(document)


def _pdf(document: pymupdf.Document):
    return pymupdf._as_pdf_document(document)  # noqa: SLF001


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


# * 3. Referencias en cache -------------------------------------------------------


def reset_page_refs(document: pymupdf.Document) -> None:
    """Invalida los ``Page`` en cache (apuntarian a otra pagina tras mover, insertar o deshacer)."""
    document._reset_page_refs()  # noqa: SLF001


# * 4. Posicion del journal -------------------------------------------------------


def journal_step(document: pymupdf.Document) -> int:
    """Operaciones aplicadas en el journal (MuPDF no registra las vacias)."""
    return document.journal_position()[0]


# * 5. Cache de fuentes -----------------------------------------------------------


def prepare_font_cache(document: pymupdf.Document) -> None:
    """
    Crea la fuente Helvetica de los textos libres antes de activar el historial.

    MuPDF guarda en una cache el objeto de cada fuente que agrega. Si se crea
    dentro de una operacion y esa operacion se deshace, el objeto desaparece
    pero la cache lo sigue usando: el siguiente texto queda apuntando a un
    objeto inexistente ("cannot find object in xref"). Creada aqui, fuera del
    historial, ningun deshacer la borra. No cambia nada visible: la anotacion
    temporal se elimina y la fuente, si no se usa, no se guarda (``garbage``).
    """
    if not document.page_count:
        return
    page = document[0]
    had_annots = document.xref_get_key(page.xref, "Annots")[0] != "null"
    try:
        page.delete_annot(page.add_freetext_annot((0, 0, 50, 20), "x", fontname="helv"))
    except (RuntimeError, ValueError) as error:  # PDF raro: los textos funcionan igual, con el aviso
        logger.warning("No se pudo preparar la fuente de los textos: %s", error)
        return
    if not had_annots:
        document.xref_set_key(page.xref, "Annots", "null")


# * 7. Fuente para escribir texto dentro del historial ------------------------------

TEXT_FONT = "helv"


def ensure_text_font(page: pymupdf.Page) -> None:
    """
    Deja la fuente Helvetica (``helv``) en los recursos de la pagina con las
    primitivas de MuPDF, para que ``insert_text`` no tenga que insertarla. El
    objeto de la fuente sale de la cache preparada por ``prepare_font_cache``
    (creada fuera del historial), asi deshacer no lo borra.
    """
    if any(font[4] == TEXT_FONT for font in page.get_fonts()):
        return
    pdf = _pdf(page.parent)
    font = mupdf.pdf_add_simple_font(pdf, mupdf.fz_new_base14_font("Helvetica"), mupdf.PDF_SIMPLE_ENCODING_LATIN)
    page_obj = mupdf.pdf_lookup_page_obj(pdf, page.number)
    resources = mupdf.pdf_dict_get_inheritable(page_obj, mupdf.PDF_ENUM_NAME_Resources)
    if not mupdf.pdf_is_dict(resources):
        resources = mupdf.pdf_dict_put_dict(page_obj, mupdf.PDF_ENUM_NAME_Resources, 2)
    fonts = mupdf.pdf_dict_get(resources, mupdf.PDF_ENUM_NAME_Font)
    if not mupdf.pdf_is_dict(fonts):
        fonts = mupdf.pdf_dict_put_dict(resources, mupdf.PDF_ENUM_NAME_Font, 2)
    mupdf.pdf_dict_puts(fonts, TEXT_FONT, font)


# * 6. Cifrado sin tocar la clave ---------------------------------------------------


def was_encrypted(document: pymupdf.Document) -> bool:
    """
    El PDF estaba cifrado. No usa ``needs_pass``: tras autenticar, MuPDF
    reintenta con contrasena vacia y el documento pasa a leerse en blanco.
    """
    return bool((document.metadata or {}).get("encryption"))
