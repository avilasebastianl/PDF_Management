"""
Organizar paginas (fase 2): rotar, eliminar, mover, insertar otro PDF o una
pagina en blanco, con deshacer/rehacer y Guardar como.
"""

import pymupdf
import pytest

from conftest import make_pdf, page_texts
from pdfmanagement import core
from pdfmanagement.core.editing import DocumentSession, SearchOptions, iter_search
from pdfmanagement.core.editing.text import page_words


def labels(session: DocumentSession) -> list[str]:
    """Texto de cada pagina con su rotacion: ``["Pagina 1", "Pagina 2@90"]``."""
    result = []
    for page in session.document:
        text = " ".join(word[4] for word in page_words(page))
        result.append(text + (f"@{page.rotation}" if page.rotation else ""))
    return result


@pytest.fixture
def session(tmp_path):
    opened = DocumentSession.open(make_pdf(tmp_path / "cinco.pdf", 5))
    yield opened
    opened.close()


def test_rotate_undo_redo(session):
    assert session.rotate([0, 2], 90) == "Rotar 2 paginas a la derecha"
    assert labels(session)[:3] == ["Pagina 1@90", "Pagina 2", "Pagina 3@90"]
    assert session.rotate([0], -90) == "Rotar pagina 1 a la izquierda"
    assert labels(session)[0] == "Pagina 1"
    assert session.undo() == "Rotar pagina 1 a la izquierda"
    assert labels(session)[0] == "Pagina 1@90"
    session.undo()
    assert not session.modified and labels(session)[0] == "Pagina 1"
    session.redo()
    assert labels(session)[2] == "Pagina 3@90" and session.modified


def test_text_and_search_work_on_rotated_pages_with_history(session):
    """get_text de PyMuPDF cambia la rotacion al extraer: con historial fallaba."""
    session.rotate([1], 90)
    assert [word[4] for word in session.words(1)] == ["Pagina", "2"]
    width, height = session.page_rect(1).width, session.page_rect(1).height
    x0, y0, x1, y1, *_ = session.words(1)[0]
    assert 0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height, "coordenadas de la pagina tal como se ve"
    hits = [hit for _page, page_hits in iter_search(session.document, "pagina 2") for hit in page_hits]
    assert [hit.page for hit in hits] == [1]
    exact = list(iter_search(session.document, "Pagina", SearchOptions(match_case=True)))
    assert sum(len(page_hits) for _page, page_hits in exact) == 5


def test_delete_pages_and_keep_at_least_one(session):
    assert session.delete([1, 3]) == "Eliminar 2 paginas"
    assert labels(session) == ["Pagina 1", "Pagina 3", "Pagina 5"]
    with pytest.raises(core.InvalidInputError):
        session.delete([0, 1, 2])
    with pytest.raises(core.InvalidInputError):
        session.delete([7])
    session.undo()
    assert session.page_count == 5


@pytest.mark.parametrize(
    ("pages", "target", "expected", "new_indices"),
    [
        ([0], 5, [2, 3, 4, 5, 1], [4]),          # al final
        ([4], 0, [5, 1, 2, 3, 4], [0]),          # al principio
        ([0, 1], 4, [3, 4, 1, 2, 5], [2, 3]),    # bloque hacia adelante
        ([1, 3], 0, [2, 4, 1, 3, 5], [0, 1]),    # paginas sueltas juntas
        ([2], 1, [1, 3, 2, 4, 5], [1]),
    ],
)
def test_move_pages(session, pages, target, expected, new_indices):
    assert session.move(pages, target) == new_indices
    assert labels(session) == [f"Pagina {n}" for n in expected]
    session.undo()
    assert labels(session) == [f"Pagina {n}" for n in range(1, 6)]


def test_move_to_same_place_records_nothing(session):
    assert session.move([2], 2) == [2]
    assert session.move([2], 3) == [2]
    assert not session.history.can_undo


def test_insert_pdf_with_rotation_images_and_annotations(session, tmp_path):
    other = pymupdf.open()
    for number in (1, 2):
        page = other.new_page()
        page.insert_text((72, 72), f"Anexo {number}", fontsize=20)
    other[0].insert_image(pymupdf.Rect(100, 100, 200, 200), pixmap=pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), 0))
    other[0].add_text_annot((300, 300), "revisar")
    other[0].insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(10, 10, 60, 30), "uri": "https://example.com"})
    other[0].insert_link({"kind": pymupdf.LINK_GOTO, "from": pymupdf.Rect(10, 40, 60, 60), "page": 1})
    other[1].set_rotation(180)
    source = tmp_path / "anexo.pdf"
    other.save(source)
    other.close()

    assert session.insert_pdf(source, 2) == 2
    assert labels(session) == ["Pagina 1", "Pagina 2", "Anexo 1", "Anexo 2@180", "Pagina 3", "Pagina 4", "Pagina 5"]
    inserted = session.document[2]
    assert len(inserted.get_images()) == 1
    assert [annot.type[1] for annot in inserted.annots()] == ["Text"]
    assert [link.get("uri") for link in inserted.get_links()] == ["https://example.com"], "enlaces internos descartados"
    assert session.history.undo_label == "Insertar 2 paginas de anexo.pdf"
    session.undo()
    assert session.page_count == 5
    session.redo()
    saved = session.save_as(tmp_path / "con_anexo.pdf")
    assert page_texts(saved)[2:4] == ["Anexo 1", "Anexo 2"]


def test_insert_protected_pdf_asks_for_password(session, tmp_path):
    locked = core.lock_pdf(make_pdf(tmp_path / "otro.pdf", 1), tmp_path / "otro_protegido.pdf", "clave")
    with pytest.raises(core.PasswordRequiredError):
        session.insert_pdf(locked, 0)
    with pytest.raises(core.WrongPasswordError):
        session.insert_pdf(locked, 0, "mala")
    assert session.insert_pdf(locked, 0, "clave") == 1
    assert session.page_count == 6 and not session.document[0].parent.is_encrypted


def test_insert_blank_page_uses_neighbor_size(tmp_path):
    session = DocumentSession.open(make_pdf(tmp_path / "apaisado.pdf", 2, width=842, height=595))
    session.insert_blank(1)
    assert session.page_count == 3
    assert (session.page_rect(1).width, session.page_rect(1).height) == (842, 595)
    assert session.words(1) == []
    session.insert_blank(3, (300, 400))
    assert session.page_rect(3).width == 300
    session.close()


def test_modified_tracks_the_saved_state(session, tmp_path):
    session.rotate([0], 90)
    session.save_as(tmp_path / "v1.pdf")
    assert not session.modified
    session.rotate([1], 90)
    assert session.modified
    session.undo()
    assert not session.modified, "deshacer hasta lo guardado = sin cambios"
    session.undo()
    assert session.modified
    session.delete([4])  # el estado guardado ya no se puede alcanzar
    session.undo()
    assert session.modified
    session.redo()
    assert session.modified


def test_edits_on_protected_document_keep_encryption(tmp_path):
    locked = core.lock_pdf(make_pdf(tmp_path / "base.pdf", 3), tmp_path / "base_protegido.pdf", "clave123")
    session = DocumentSession.open(locked, "clave123")
    session.rotate([0], 90)
    session.move([2], 0)  # 3, 1, 2
    session.delete([2])  # 3, 1
    output = session.save_as(tmp_path / "editado.pdf")
    session.close()
    with pytest.raises(core.PasswordRequiredError):
        core.open_document(output)
    assert page_texts(output, "clave123") == ["Pagina 3", "Pagina 1"]
    with core.open_document(output, "clave123") as document:
        assert document[1].rotation == 90


def test_visible_text_helper_uses_internal_api():
    """``text.visible_textpage`` usa una API interna de PyMuPDF: avisar si desaparece."""
    assert hasattr(pymupdf.Page, "_get_textpage")
