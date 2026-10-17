"""
Herramientas: comprimir, dividir, numerar paginas y marca de agua (core/tools.py).
"""

import io

import pymupdf
import pytest
from conftest import make_pdf, page_texts
from PIL import Image

from pdfmanagement import core
from pdfmanagement.core import tools
from pdfmanagement.core.editing.text import page_search


@pytest.fixture
def photo_pdf(tmp_path):
    """PDF con una foto grande (ruido: no se comprime sola) en cada pagina."""
    import random

    random.seed(1)
    image = Image.frombytes("RGB", (1600, 1200), bytes(random.getrandbits(8) for _ in range(1600 * 1200 * 3)))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    document = pymupdf.open()
    for _ in range(2):
        page = document.new_page()
        page.insert_image(pymupdf.Rect(36, 36, 300, 236), stream=buffer.getvalue())
    path = tmp_path / "fotos.pdf"
    document.save(path)
    return path


def test_compress_reduces_large_images(photo_pdf, tmp_path):
    result = tools.compress_pdf(photo_pdf, tmp_path / "liviano.pdf", "alta")
    assert result.size_after < result.size_before * 0.5, (result.size_before, result.size_after)
    assert result.saved_ratio > 0.5
    with pymupdf.open(result.path) as document:
        assert document.page_count == 2 and document[0].get_images()
    low = tools.compress_pdf(photo_pdf, tmp_path / "baja.pdf", "baja")
    assert low.size_after <= low.size_before
    with pytest.raises(core.InvalidInputError):
        tools.compress_pdf(photo_pdf, tmp_path / "x.pdf", "maxima")
    with pytest.raises(core.InvalidInputError):
        tools.compress_pdf(photo_pdf, photo_pdf, "media")  # nunca sobre el original


def test_compress_keeps_password(tmp_path):
    locked = core.lock_pdf(make_pdf(tmp_path / "base.pdf", 2), tmp_path / "protegido.pdf", "clave123")
    with pytest.raises(core.PasswordRequiredError):
        tools.compress_pdf(locked, tmp_path / "salida.pdf")
    result = tools.compress_pdf(locked, tmp_path / "salida.pdf", password="clave123")
    with pytest.raises(core.PasswordRequiredError):
        core.open_document(result.path)
    assert page_texts(result.path, "clave123") == ["Pagina 1", "Pagina 2"]


def test_split_by_ranges_every_n_and_bookmarks(tmp_path):
    source = make_pdf(tmp_path / "libro.pdf", 7)
    parts = tools.split_pdf(source, tmp_path / "rangos", "rangos", "1-2; 5; 6-")
    assert [page_texts(part) for part in parts] == [["Pagina 1", "Pagina 2"], ["Pagina 5"], ["Pagina 6", "Pagina 7"]]
    every = tools.split_pdf(source, tmp_path / "cada", "cada", 3)
    assert [len(page_texts(part)) for part in every] == [3, 3, 1]
    assert every[0].name == "libro_parte1.pdf"
    with pymupdf.open(source) as document:
        document.set_toc([[1, "Introducción", 1], [2, "Detalle", 2], [1, "Anexo: datos/2026", 4]])
        document.save(tmp_path / "con_indice.pdf")
    chapters = tools.split_pdf(tmp_path / "con_indice.pdf", tmp_path / "capitulos", "marcadores")
    assert [part.name for part in chapters] == ["con_indice_Introducción.pdf", "con_indice_Anexo_datos2026.pdf"]
    assert [len(page_texts(part)) for part in chapters] == [3, 4]
    with pytest.raises(core.InvalidInputError):
        tools.split_pdf(source, tmp_path / "x", "marcadores")
    with pytest.raises(core.InvalidInputError):
        tools.split_pdf(source, tmp_path / "x", "cada", 0)


@pytest.mark.parametrize("rotation", [0, 90])
def test_page_numbers_where_they_are_seen(tmp_path, rotation):
    source = make_pdf(tmp_path / "doc.pdf", 3, rotation=rotation)
    output = tools.add_page_numbers(source, tmp_path / "numerado.pdf", position="abajo-derecha", start=5)
    with pymupdf.open(output) as document:
        page = document[1]
        [hit] = page_search(page, "Página 6 de 7")
        assert hit.x1 > page.rect.width * 0.6 and hit.y1 > page.rect.height * 0.9, "abajo a la derecha, como se ve"
    custom = tools.add_page_numbers(source, tmp_path / "custom.pdf", template="- {n} -", pages="2-3")
    assert "- 1 -" in page_texts(custom)[1] and page_texts(custom)[0] == "Pagina 1"
    with pytest.raises(core.InvalidInputError):
        tools.add_page_numbers(source, tmp_path / "x.pdf", template="{pagina}")


def test_watermark_is_light_and_centered(tmp_path):
    source = make_pdf(tmp_path / "doc.pdf", 2)
    output = tools.add_watermark(source, tmp_path / "marca.pdf", "CONFIDENCIAL", opacity=0.2)
    with pymupdf.open(output) as document:
        page = document[0]
        assert "CONFIDENCIAL" in page.get_text()
        pixmap = page.get_pixmap(dpi=40)
        center = pixmap.pixel(pixmap.width // 2, pixmap.height // 2)
        assert min(center) > 120, "la marca es clara (semitransparente), no tapa el contenido"
    with pytest.raises(core.InvalidInputError):
        tools.add_watermark(source, tmp_path / "x.pdf", "   ")


def test_cyrillic_text_uses_a_unicode_font(tmp_path):
    """En ruso la plantilla por defecto es cirilica: no debe quedar ilegible."""
    source = make_pdf(tmp_path / "doc.pdf", 2)
    numbered = tools.add_page_numbers(source, tmp_path / "num.pdf", template="Страница {n} из {total}")
    marked = tools.add_watermark(source, tmp_path / "marca.pdf", "ЧЕРНОВИК")
    assert "Страница 1 из 2" in page_texts(numbered)[0].replace(" ", " ")
    assert "ЧЕРНОВИК" in page_texts(marked)[1]
