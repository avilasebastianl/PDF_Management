"""
Pruebas de las operaciones del nucleo sobre PDFs reales generados al vuelo.
"""

import pymupdf
import pytest
from pypdf import PdfReader

from conftest import page_texts
from pdfmanagement import core


# * Unir ---------------------------------------------------------------------

def test_merge_keeps_order(pdf_factory, tmp_path):
    first = pdf_factory("a.pdf", 2)
    second = pdf_factory("b.pdf", 1)
    result = core.merge_pdfs([second, first], tmp_path / "out.pdf")
    assert page_texts(result) == ["Pagina 1", "Pagina 1", "Pagina 2"]


def test_merge_adds_bookmarks(pdf_factory, tmp_path):
    first = pdf_factory("primero.pdf", 1)
    second = pdf_factory("segundo.pdf", 2)
    result = core.merge_pdfs([first, second], tmp_path / "out.pdf", add_bookmarks=True)
    assert [item.title for item in PdfReader(result).outline] == ["primero", "segundo"]


def test_merge_ignores_duplicates(pdf_factory, tmp_path):
    document = pdf_factory("a.pdf", 2)
    result = core.merge_pdfs([document, document], tmp_path / "out.pdf")
    assert len(page_texts(result)) == 2


def test_merge_rejects_output_equal_to_input(pdf_factory):
    document = pdf_factory("a.pdf", 1)
    with pytest.raises(core.InvalidInputError):
        core.merge_pdfs([document], document)


def test_merge_requires_password_and_reports_file(pdf_factory, tmp_path):
    locked = core.lock_pdf(pdf_factory("a.pdf", 1), tmp_path / "locked.pdf", "secreta")
    plain = pdf_factory("b.pdf", 1)
    with pytest.raises(core.PasswordRequiredError) as raised:
        core.merge_pdfs([plain, locked], tmp_path / "out.pdf")
    assert raised.value.file_path == locked

    result = core.merge_pdfs([plain, locked], tmp_path / "out.pdf", passwords={locked: "secreta"})
    assert len(page_texts(result)) == 2


def test_failed_operation_does_not_leave_partial_files(pdf_factory, tmp_path):
    locked = core.lock_pdf(pdf_factory("a.pdf", 1), tmp_path / "locked.pdf", "secreta")
    output = tmp_path / "salida" / "out.pdf"
    with pytest.raises(core.PasswordRequiredError):
        core.merge_pdfs([locked], output)
    assert list(output.parent.iterdir()) == []


# * Extraer -------------------------------------------------------------------

def test_extract_selected_pages_in_order(pdf_factory, tmp_path):
    source = pdf_factory("a.pdf", 5)
    result = core.extract_pages(source, tmp_path / "out.pdf", "4, 1-2")
    assert page_texts(result) == ["Pagina 4", "Pagina 1", "Pagina 2"]


def test_extract_adds_pdf_extension(pdf_factory, tmp_path):
    result = core.extract_pages(pdf_factory("a.pdf", 2), tmp_path / "resultado", "1")
    assert result.name == "resultado.pdf"


def test_extract_with_passwords(pdf_factory, tmp_path):
    locked = core.lock_pdf(pdf_factory("a.pdf", 3), tmp_path / "locked.pdf", "origen")
    with pytest.raises(core.PasswordRequiredError):
        core.extract_pages(locked, tmp_path / "out.pdf", "1")
    with pytest.raises(core.WrongPasswordError):
        core.extract_pages(locked, tmp_path / "out.pdf", "1", password="mala")

    result = core.extract_pages(locked, tmp_path / "out.pdf", "2-3", password="origen", output_password="final")
    assert PdfReader(result).is_encrypted
    assert page_texts(result, "final") == ["Pagina 2", "Pagina 3"]


# * Proteger -----------------------------------------------------------------

def test_lock_and_unlock_roundtrip(pdf_factory, tmp_path):
    source = pdf_factory("a.pdf", 2)
    locked = core.lock_pdf(source, tmp_path / "locked.pdf", "clave123")
    with pymupdf.open(locked) as document:
        assert document.needs_pass
        document.authenticate("clave123")
        assert "256-bit AES" in document.metadata["encryption"]

    unlocked = core.unlock_pdf(locked, tmp_path / "unlocked.pdf", "clave123")
    assert not PdfReader(unlocked).is_encrypted
    assert page_texts(unlocked) == ["Pagina 1", "Pagina 2"]


def test_lock_validations(pdf_factory, tmp_path):
    source = pdf_factory("a.pdf", 1)
    with pytest.raises(core.InvalidInputError):
        core.lock_pdf(source, tmp_path / "out.pdf", "abc")
    locked = core.lock_pdf(source, tmp_path / "locked.pdf", "clave123")
    with pytest.raises(core.InvalidInputError):
        core.lock_pdf(locked, tmp_path / "again.pdf", "clave123")


def test_unlock_validations(pdf_factory, tmp_path):
    source = pdf_factory("a.pdf", 1)
    with pytest.raises(core.InvalidInputError):
        core.unlock_pdf(source, tmp_path / "out.pdf", "x")
    locked = core.lock_pdf(source, tmp_path / "locked.pdf", "clave123")
    with pytest.raises(core.WrongPasswordError):
        core.unlock_pdf(locked, tmp_path / "out.pdf", "incorrecta")


# * Firmar -------------------------------------------------------------------

def _image_bbox(pdf_path, page_index=0, password=None):
    with pymupdf.open(pdf_path) as document:
        if password:
            document.authenticate(password)
        page = document[page_index]
        infos = page.get_image_info()
        return [pymupdf.Rect(info["bbox"]) for info in infos], page.rotation


def test_load_signature_trims_margins(signature_png):
    image = core.load_signature(signature_png)
    assert image.size == (100, 50)


def test_load_signature_removes_paper_background(signature_jpg):
    image = core.load_signature(signature_jpg)
    assert image.getpixel((0, 0))[3] == 255 or image.height < 20
    assert image.width > 200 and image.height < 30


def test_sign_last_page_by_default(pdf_factory, signature_png, tmp_path):
    source = pdf_factory("a.pdf", 3)
    placement = core.SignaturePlacement(x=100, y=200, width=120)
    result = core.sign_pdf_with_image(source, tmp_path / "out.pdf", signature_png, placement)
    assert _image_bbox(result, 0)[0] == []
    boxes, _ = _image_bbox(result, 2)
    assert len(boxes) == 1
    assert boxes[0].x0 == pytest.approx(100, abs=0.5)
    assert boxes[0].y0 == pytest.approx(200, abs=0.5)
    assert boxes[0].width == pytest.approx(120, abs=0.5)
    assert boxes[0].height == pytest.approx(60, abs=0.5)  # relacion 2:1 tras recortar


def test_sign_specific_page_and_all_pages(pdf_factory, signature_png, tmp_path):
    source = pdf_factory("a.pdf", 3)
    second = core.sign_pdf_with_image(
        source, tmp_path / "p2.pdf", signature_png, core.SignaturePlacement(x=50, y=50, page_number=2)
    )
    assert [len(_image_bbox(second, index)[0]) for index in range(3)] == [0, 1, 0]

    every = core.sign_pdf_with_image(
        source, tmp_path / "all.pdf", signature_png, core.SignaturePlacement(x=50, y=50, all_pages=True)
    )
    assert [len(_image_bbox(every, index)[0]) for index in range(3)] == [1, 1, 1]


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_sign_rotated_pages_match_preview_coordinates(pdf_factory, signature_png, tmp_path, rotation):
    source = pdf_factory("rot.pdf", 1, rotation=rotation)
    placement = core.SignaturePlacement(x=60, y=80, width=100, page_number=1)
    result = core.sign_pdf_with_image(source, tmp_path / "out.pdf", signature_png, placement)

    with pymupdf.open(result) as document:
        page = document[0]
        pixmap = page.get_pixmap()
        # El rectangulo visible (vista previa) debe contener pixeles oscuros de la firma.
        expected = core.signature_rect(page.rect, placement, 0.5)
        center = (int((expected.x0 + expected.x1) / 2), int((expected.y0 + expected.y1) / 2))
        assert pixmap.pixel(*center)[:3] == (0, 0, 0)
        outside = (int(expected.x1 + 20), int(expected.y1 + 20))
        assert pixmap.pixel(*outside)[:3] == (255, 255, 255)


def test_signature_is_kept_inside_the_page(pdf_factory, signature_png, tmp_path):
    source = pdf_factory("a.pdf", 1, width=300, height=400)
    placement = core.SignaturePlacement(x=280, y=390, width=100, page_number=1)
    result = core.sign_pdf_with_image(source, tmp_path / "out.pdf", signature_png, placement)
    box = _image_bbox(result)[0][0]
    assert box.x1 <= 300.5 and box.y1 <= 400.5


def test_sign_keeps_encryption(pdf_factory, signature_png, tmp_path):
    locked = core.lock_pdf(pdf_factory("a.pdf", 1), tmp_path / "locked.pdf", "clave123")
    placement = core.SignaturePlacement(x=50, y=50, page_number=1)
    with pytest.raises(core.PasswordRequiredError):
        core.sign_pdf_with_image(locked, tmp_path / "out.pdf", signature_png, placement)
    result = core.sign_pdf_with_image(locked, tmp_path / "out.pdf", signature_png, placement, password="clave123")
    assert PdfReader(result).is_encrypted
    assert len(_image_bbox(result, password="clave123")[0]) == 1


def test_sign_rejects_missing_page(pdf_factory, signature_png, tmp_path):
    with pytest.raises(core.InvalidInputError):
        core.sign_pdf_with_image(
            pdf_factory("a.pdf", 2), tmp_path / "out.pdf", signature_png, core.SignaturePlacement(x=0, y=0, page_number=5)
        )


# * Informacion y utilidades --------------------------------------------------

def test_pdf_info(pdf_factory, tmp_path):
    info = core.get_pdf_info(pdf_factory("a.pdf", 4))
    assert info.page_count == 4 and not info.encrypted
    locked = core.lock_pdf(pdf_factory("b.pdf", 1), tmp_path / "locked.pdf", "clave123")
    info = core.get_pdf_info(locked)
    assert info.encrypted and info.page_count is None


def test_unique_path(tmp_path):
    target = tmp_path / "doc.pdf"
    assert core.unique_path(target) == target
    target.touch()
    assert core.unique_path(target).name == "doc (2).pdf"


def test_invalid_inputs(tmp_path):
    with pytest.raises(core.InvalidInputError):
        core.get_pdf_info(tmp_path / "no_existe.pdf")
    not_pdf = tmp_path / "nota.txt"
    not_pdf.write_text("hola")
    with pytest.raises(core.InvalidInputError):
        core.extract_pages(not_pdf, tmp_path / "out.pdf", "1")
    fake_pdf = tmp_path / "falso.pdf"
    fake_pdf.write_text("no soy un pdf")
    with pytest.raises(core.InvalidInputError):
        core.extract_pages(fake_pdf, tmp_path / "out.pdf", "1")
