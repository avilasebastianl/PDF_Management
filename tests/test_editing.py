"""
Nucleo de edicion: sesion de documento, historial (deshacer/rehacer),
guardado seguro y busqueda.
"""

import pymupdf
import pytest

from pdfmanagement import core, recent
from pdfmanagement.core.editing import DocumentSession, SearchOptions, iter_search


@pytest.fixture
def text_pdf(tmp_path):
    document = pymupdf.open()
    lines = [
        "Contrato de servicios entre las partes.",
        "El CONTRATO tiene vigencia de un ano.",
        "Subcontrato no permitido sin autorizacion.",
    ]
    for page_number in range(3):
        page = document.new_page()
        for line_number, line in enumerate(lines):
            page.insert_text((72, 80 + line_number * 20), f"{line} Pagina {page_number + 1}.", fontsize=11)
    document.set_toc([[1, "Inicio", 1], [2, "Detalle", 2], [1, "Final", 3]])
    path = tmp_path / "contrato.pdf"
    document.save(path)
    return path


def test_open_reads_pages_toc_and_properties(text_pdf):
    session = DocumentSession.open(text_pdf)
    assert session.page_count == 3
    assert session.table_of_contents() == [(1, "Inicio", 1), (2, "Detalle", 2), (1, "Final", 3)]
    props = session.properties()
    assert props.page_count == 3 and not props.encrypted and not props.has_signatures
    assert len(session.page_sizes()) == 3
    assert session.words(0)[0][4] == "Contrato"
    session.close()


def test_open_protected_requires_password(text_pdf, tmp_path):
    locked = core.lock_pdf(text_pdf, tmp_path / "locked.pdf", "clave123")
    with pytest.raises(core.PasswordRequiredError):
        DocumentSession.open(locked)
    with pytest.raises(core.WrongPasswordError):
        DocumentSession.open(locked, "mala")
    session = DocumentSession.open(locked, "clave123")
    assert session.encrypted and session.page_count == 3
    session.close()


def test_history_undo_redo_and_modified_flag(text_pdf):
    changes = []
    session = DocumentSession.open(text_pdf, on_change=lambda: changes.append(1))
    assert not session.modified
    with session.history.operation("Rotar pagina 1"):
        session.document[0].set_rotation(90)
    with session.history.operation("Borrar pagina 3"):
        session.document.delete_page(2)
    assert session.modified and session.history.undo_label == "Borrar pagina 3"
    assert session.history.undo() == "Borrar pagina 3" and session.page_count == 3
    assert session.history.undo() == "Rotar pagina 1" and session.document[0].rotation == 0
    assert not session.modified
    assert session.history.redo() == "Rotar pagina 1" and session.document[0].rotation == 90
    assert len(changes) == 5
    session.close()


def test_failed_operation_is_rolled_back(text_pdf):
    session = DocumentSession.open(text_pdf)
    with pytest.raises(RuntimeError):
        with session.history.operation("Fallida"):
            session.document[0].set_rotation(180)
            raise RuntimeError("boom")
    assert session.document[0].rotation == 0
    assert not session.history.can_undo
    session.close()


def test_save_as_keeps_original_and_history(text_pdf, tmp_path):
    session = DocumentSession.open(text_pdf)
    with session.history.operation("Rotar"):
        session.document[0].set_rotation(90)
    output = session.save_as(tmp_path / "copia.pdf")
    assert pymupdf.open(output)[0].rotation == 90
    assert pymupdf.open(text_pdf)[0].rotation == 0, "el original no se modifica"
    assert not session.modified
    assert session.history.undo() == "Rotar" and session.document[0].rotation == 0, (
        "se puede deshacer despues de guardar"
    )
    with pytest.raises(core.InvalidInputError):
        session.save_as(text_pdf)  # nunca sobre el original
    session.close()


def test_save_as_keeps_encryption(text_pdf, tmp_path):
    locked = core.lock_pdf(text_pdf, tmp_path / "locked.pdf", "clave123")
    session = DocumentSession.open(locked, "clave123")
    protected = session.save_as(tmp_path / "copia_protegida.pdf")
    plain = session.save_as(tmp_path / "copia_libre.pdf", keep_encryption=False)
    assert pymupdf.open(protected).needs_pass
    assert not pymupdf.open(plain).needs_pass
    session.close()


def test_search_modes(text_pdf):
    session = DocumentSession.open(text_pdf)
    document = session.document

    def count(query, **options):
        return sum(len(hits) for _page, hits in iter_search(document, query, SearchOptions(**options)))

    assert count("contrato") == 9  # Contrato, CONTRATO y Subcontrato en 3 paginas
    assert count("contrato", whole_words=True) == 6
    assert count("Contrato", match_case=True) == 3
    assert count("CONTRATO tiene", match_case=True) == 3  # frase
    assert count("inexistente") == 0
    first = next(iter_search(document, "vigencia"))
    assert first[0] == 0 and first[1][0].context
    order = [page for page, _hits in iter_search(document, "contrato", start_page=2)]
    assert order == [2, 0, 1], "la busqueda empieza en la pagina actual y da la vuelta"
    session.close()


def test_recent_files(tmp_path, monkeypatch, text_pdf):
    from pdfmanagement import paths

    monkeypatch.setattr(paths, "CONFIG_DIR", tmp_path / "config")
    other = tmp_path / "otro.pdf"
    other.write_bytes(text_pdf.read_bytes())
    recent.add_recent(text_pdf)
    recent.add_recent(other)
    recent.add_recent(text_pdf)
    assert recent.load_recent() == [text_pdf.resolve(), other.resolve()]
    other.unlink()
    assert recent.load_recent() == [text_pdf.resolve()], "los archivos borrados desaparecen"
