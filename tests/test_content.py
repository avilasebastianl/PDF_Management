"""
Editar el contenido de la pagina (fase 4): reemplazar texto, texto e imagen
fijos y tapar de forma definitiva. Tambien en paginas giradas y con deshacer.
"""

import pymupdf
import pytest
from conftest import make_pdf
from PIL import Image

from pdfmanagement import core
from pdfmanagement.core.editing import DocumentSession, content
from pdfmanagement.core.editing.text import page_search, page_words


@pytest.fixture(params=[0, 90], ids=["normal", "girada"])
def session(request, tmp_path):
    opened = DocumentSession.open(make_pdf(tmp_path / "doc.pdf", 2, rotation=request.param))
    yield opened
    opened.close()


def words(session, page=0):
    return [word[4] for word in page_words(session.document[page])]


def test_replace_text_keeps_size_and_position(session):
    page = session.document[0]
    [old] = page_search(page, "Pagina 1")
    session.replace_text(0, [old], "Página reemplazada")
    assert words(session) == ["Página", "reemplazada"]
    page = session.document[0]
    [new] = page_search(page, "Página reemplazada")
    thickness = min(new.width, new.height), min(old.width, old.height)  # alto de la linea, sea cual sea su direccion
    assert abs(new.x0 - old.x0) < 3 and abs(new.y0 - old.y0) < 3, "mismo lugar"
    assert abs(thickness[0] - thickness[1]) < 3, "mismo tamaño de letra"
    assert session.history.undo_label == "Reemplazar texto (página 1)"
    session.undo()
    assert words(session) == ["Pagina", "1"]
    with pytest.raises(core.InvalidInputError):
        session.replace_text(0, [], "x")


def test_fixed_text_is_part_of_the_page(session):
    session.add_fixed_text(0, (100, 300), "Aprobado", 16, (0.8, 0, 0))
    page = session.document[0]
    [found] = page_search(page, "Aprobado")
    assert abs(found.x0 - 100) < 3 and abs(found.y0 - 300) < 6
    assert session.annotations(0) == [], "no es una anotacion: es contenido"


def test_image_is_upright_where_it_is_seen(session, tmp_path):
    image = Image.new("RGB", (100, 50), (255, 0, 0))
    image.paste((0, 0, 255), (50, 0, 100, 50))
    path = tmp_path / "logo.png"
    image.save(path)
    session.add_image(0, pymupdf.Rect(100, 100, 300, 200), path)
    pixmap = session.document[0].get_pixmap()
    left, right = pixmap.pixel(120, 150), pixmap.pixel(280, 150)
    assert left[0] > 200 and left[2] < 60 and right[2] > 200 and right[0] < 60, "roja a la izquierda, azul a la derecha"
    with pytest.raises(core.InvalidInputError):
        session.add_image(0, pymupdf.Rect(100, 100, 300, 200), tmp_path / "no_existe.png")


def test_redaction_removes_text_for_good(session, tmp_path):
    page = session.document[0]
    [hit] = page_search(page, "Pagina 1")
    session.redact(0, hit + (-2, -2, 2, 2))
    assert words(session) == []
    output = session.save_as(tmp_path / "tapado.pdf")
    with pymupdf.open(output) as document:
        assert "Pagina" not in document[0].get_text(), "no queda en el archivo guardado"
        visible = document[0]
        pixmap = visible.get_pixmap()
        x, y = int((hit.x0 + hit.x1) / 2), int((hit.y0 + hit.y1) / 2)
        assert min(pixmap.pixel(x, y)) > 240, "queda del color del fondo (blanco), sin bloque negro"


def test_replace_text_in_a_pdf_with_its_own_font(tmp_path):
    """PDF real: la fuente no es Helvetica (antes fallaba dentro del historial)."""
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "Contrato vigente", fontname="tiro", fontsize=14)
    path = tmp_path / "times.pdf"
    document.save(path)
    session = DocumentSession.open(path)
    page = session.document[0]
    [hit] = page_search(page, "vigente")
    session.replace_text(0, [hit], "vencido")
    session.add_fixed_text(0, (72, 200), "Nota", 12, (0, 0, 0))
    assert [word[4] for word in page_words(session.document[0])] == ["Contrato", "vencido", "Nota"]
    session.undo()
    session.undo()
    session.replace_text(0, [hit], "renovado")
    assert "renovado" in [word[4] for word in page_words(session.document[0])]
    session.close()


def test_text_helvetica_cannot_write_is_rejected(session):
    with pytest.raises(core.InvalidInputError, match="Helvetica"):
        session.add_fixed_text(0, (72, 200), "Привет", 12, (0, 0, 0))
    assert not session.history.can_undo, "no se cambio nada"
    assert content.helvetica_can_write("Página año €")


def _dark_band_pdf(tmp_path, text_color):
    """Franja oscura con texto encima (como la barra lateral de un CV)."""
    path = tmp_path / "franja.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.draw_rect((40, 60, 300, 120), color=None, fill=(0.08, 0.12, 0.2))
    page.insert_text((60, 95), "CONTACTO", fontsize=14, color=text_color)
    document.save(path)
    document.close()
    return path


def test_replaced_text_stays_readable_on_a_dark_band(tmp_path):
    session = DocumentSession.open(_dark_band_pdf(tmp_path, (0.9, 0.9, 0.9)))
    page = session.document[0]
    [old] = page_search(page, "CONTACTO")
    background, ink = content.visible_colors(page, old)
    assert content.contrast(background, (0.08, 0.12, 0.2)) < 1.2 and ink is not None and sum(ink) > 2
    session.replace_text(0, [old], "NUEVO")
    [span] = [s for b in session.document[0].get_text("dict")["blocks"] for line in b["lines"] for s in line["spans"]]
    assert span["color"] != 0, "texto claro sobre fondo oscuro: no negro"


def test_declared_black_text_on_dark_band_uses_the_visible_color(tmp_path):
    path = _dark_band_pdf(tmp_path, (0.0, 0.0, 0.0))
    session = DocumentSession.open(path)
    [old] = page_search(session.document[0], "CONTACTO")
    session.replace_text(0, [old], "NUEVO")
    [span] = [s for b in session.document[0].get_text("dict")["blocks"] for line in b["lines"] for s in line["spans"]]
    assert span["color"] == 0xFFFFFF, "negro sobre la franja no se ve: se escribe en blanco"


def test_redact_covers_with_the_background_color(tmp_path):
    session = DocumentSession.open(_dark_band_pdf(tmp_path, (0.9, 0.9, 0.9)))
    [old] = page_search(session.document[0], "CONTACTO")
    session.redact(0, old + (-2, -2, 2, 2))
    page = session.document[0]
    assert "CONTACTO" not in page.get_text()
    pixmap = page.get_pixmap(dpi=72)
    red, green, blue = pixmap.pixel(int(old.x0 + 10), int((old.y0 + old.y1) / 2))
    assert blue > red and max(red, green, blue) < 90, "queda del color de la franja, no un bloque negro"
