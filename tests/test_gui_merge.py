"""
Unir con marca de agua, firma y vista previa del resultado (una sola barra de
desplazamiento). Requiere pantalla.
"""

import pymupdf
import pytest
from conftest import make_pdf, pump
from PIL import Image, ImageDraw

from pdfmanagement.gui import finish_controls


@pytest.fixture
def merge_page(gui_app, tmp_path, monkeypatch):
    signature = tmp_path / "firma.png"
    image = Image.new("RGB", (300, 120), "white")
    ImageDraw.Draw(image).line((20, 90, 280, 30), fill="black", width=8)
    image.save(signature)
    monkeypatch.setattr(finish_controls.signatures, "list_signatures", lambda: [signature])
    gui_app.show_page("Unir")
    page = gui_app.pages["Unir"]
    page._clear()
    pump(gui_app, timeout=0.2)
    page._add_files([make_pdf(tmp_path / "a.pdf", 2), make_pdf(tmp_path / "b.pdf", 3)])
    pump(gui_app, lambda: all(entry.info is not None for entry in page.entries), timeout=5)
    yield page
    page.add_watermark.deselect()
    page.add_signature.deselect()
    page._on_finish_toggled(log=False)
    page._clear()


def test_merge_page_scrolls_as_one(merge_page):
    assert merge_page.scrollable, "la seccion tiene una sola barra de desplazamiento"
    assert not hasattr(merge_page.list_frame, "_parent_canvas"), "la lista no tiene barra propia"


def test_preview_and_merge_with_watermark_and_signature(merge_page, gui_app, tmp_path):
    merge_page.refresh_preview()
    assert merge_page.preview.image is not None, "con archivos se ve la primera pagina"
    merge_page.add_watermark.select()
    merge_page.add_signature.select()
    merge_page._on_finish_toggled(log=False)
    merge_page.watermark.mark_text.set("BORRADOR")
    merge_page.preview_page.set("Última página")
    merge_page.refresh_preview()
    assert merge_page.preview.image is not None
    output = tmp_path / "unido.pdf"
    merge_page.output_field.set(output)
    merge_page._merge()
    pump(gui_app, lambda: not gui_app.runner.busy, timeout=0.5)
    pump(gui_app, lambda: output.exists() and not gui_app.runner.busy, timeout=10)
    with pymupdf.open(output) as document:
        assert document.page_count == 5
        assert all("BORRADOR" in page.get_text() for page in document)
        assert len(document[4].get_image_info()) == 1 and not document[0].get_image_info(), "firma en la ultima"


def test_signature_without_certificate_is_reported(merge_page, gui_app, monkeypatch, tmp_path):
    merge_page.output_field.set(tmp_path / "sin_certificado.pdf")  # que no pregunte si reemplazar
    errors = []
    monkeypatch.setattr(gui_app, "show_error", errors.append)
    merge_page.add_signature.select()
    merge_page._on_finish_toggled(log=False)
    merge_page.signature.kind.set("Firma digital")
    merge_page.signature._on_kind("Firma digital")
    merge_page._merge()
    assert errors and "certificado" in str(errors[0])


def test_preview_switches_between_image_and_message_safely(merge_page, gui_app):
    """Antes: 'image pyimageN does not exist' al pasar de la imagen a un mensaje."""
    import gc

    merge_page.refresh_preview()
    assert merge_page.preview.image is not None
    merge_page.preview.set_message("sin vista previa")
    gc.collect()  # la imagen anterior se libera de verdad
    merge_page.preview.configure(width=200)  # cualquier redibujo fallaba
    merge_page.refresh_preview()
    gc.collect()
    merge_page.preview.set_message("otra vez")
    assert merge_page.preview.image is None
    pump(gui_app, timeout=0.5)  # la vista previa programada vuelve a dibujarse sin errores
