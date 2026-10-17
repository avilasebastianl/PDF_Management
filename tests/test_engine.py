"""
Puente con PyMuPDF (``core/editing/engine.py``): una prueba por cada
comportamiento de PyMuPDF/MuPDF que la aplicacion rodea. Si una version nueva
cambia alguno, falla aqui con un mensaje claro en lugar de romper el visor.
"""

import pymupdf
import pytest
from conftest import make_pdf

from pdfmanagement import core
from pdfmanagement.core.editing import engine


def journaled(document: pymupdf.Document) -> pymupdf.Document:
    document.journal_enable()
    return document


def test_installed_version_is_the_verified_one():
    assert engine.check_version(), f"PyMuPDF {pymupdf.__version__}: revisar los puntos de engine.py"


def test_get_text_changes_rotation_but_visible_textpage_does_not(tmp_path):
    """Punto 1: get_text gira la pagina para extraer (falla con historial)."""
    document = journaled(pymupdf.open(make_pdf(tmp_path / "girado.pdf", 1, rotation=90)))
    page = document[0]
    with pytest.raises(Exception, match="operation"):
        page.get_text("words")
    words = engine.visible_textpage(page, pymupdf.TEXTFLAGS_WORDS).extractWORDS()
    assert [word[4] for word in words] == ["Pagina", "1"]
    assert all(0 <= word[0] < word[2] <= page.rect.width for word in words), "coordenadas visibles"


def test_insert_pdf_fails_in_a_journal_operation_but_graft_works(tmp_path):
    """Punto 2: insert_pdf / new_page no admiten el journal; las primitivas si."""
    document = journaled(pymupdf.open(make_pdf(tmp_path / "base.pdf", 2)))
    other = pymupdf.open(make_pdf(tmp_path / "otro.pdf", 1))
    document.journal_start_op("insert_pdf")
    with pytest.raises(Exception, match="undo/redo during an operation"):
        document.insert_pdf(other)
    document.journal_stop_op()
    document.journal_start_op("graft")
    engine.graft_pages(document, pymupdf.open("pdf", other.tobytes()), 1, [0])
    engine.add_blank_page(document, 0, 300, 400)
    document.journal_stop_op()
    assert document.page_count == 4 and document[0].rect.width == 300
    document.journal_undo()
    engine.reset_page_refs(document)
    assert document.page_count == 2


def test_empty_journal_operation_is_not_recorded(tmp_path):
    """Punto 4: MuPDF descarta las operaciones vacias."""
    document = journaled(pymupdf.open(make_pdf(tmp_path / "doc.pdf", 1)))
    before = engine.journal_step(document)
    document.journal_start_op("vacia")
    document.journal_stop_op()
    assert engine.journal_step(document) == before
    document.journal_start_op("rotar")
    document[0].set_rotation(90)
    document.journal_stop_op()
    assert engine.journal_step(document) == before + 1


def test_font_cache_survives_undo_only_when_prepared(tmp_path):
    """Punto 5: sin preparar la fuente, un texto tras deshacer otro apunta a un objeto borrado."""
    for prepared in (False, True):
        document = pymupdf.open(make_pdf(tmp_path / f"fuente{prepared}.pdf", 1))
        if prepared:
            engine.prepare_font_cache(document)
        journaled(document)
        pymupdf.TOOLS.reset_mupdf_warnings()
        for text in ("uno", "dos"):
            document.journal_start_op(text)
            page = document[0]
            page.add_freetext_annot((50, 50, 200, 80), text)
            document.journal_stop_op()
            if text == "uno":
                document.journal_undo()
        document[0].get_pixmap()
        broken = "cannot find object" in pymupdf.TOOLS.mupdf_warnings()
        assert broken is not prepared


def test_needs_pass_after_authenticating_blanks_the_document(tmp_path):
    """Punto 6: needs_pass reautentica con contrasena vacia; was_encrypted no."""
    locked = core.lock_pdf(make_pdf(tmp_path / "base.pdf", 1), tmp_path / "cifrado.pdf", "clave123")
    document = core.open_document(locked, "clave123")
    assert engine.was_encrypted(document)
    assert document[0].get_text().strip() == "Pagina 1"
    _ = document.needs_pass
    assert document[0].get_text().strip() == "", "si deja de pasar, needs_pass ya es seguro"
    assert not engine.was_encrypted(pymupdf.open(make_pdf(tmp_path / "plano.pdf", 1)))
