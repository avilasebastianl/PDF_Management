"""
Unir con marca de agua, firma y vista previa del resultado (una sola barra de
desplazamiento). Requiere pantalla.
"""

import pymupdf
import pytest
from conftest import make_pdf, pump


@pytest.fixture
def merge_page(gui_app, tmp_path):
    gui_app.show_page("Unir")
    page = gui_app.pages["Unir"]
    page._clear()
    pump(gui_app, timeout=0.2)
    page._add_files([make_pdf(tmp_path / "a.pdf", 2), make_pdf(tmp_path / "b.pdf", 3)])
    pump(gui_app, lambda: all(entry.info is not None for entry in page.entries), timeout=5)
    yield page
    page.add_watermark.deselect()
    page._on_finish_toggled(log=False)
    page._clear()


def test_merge_page_scrolls_as_one(merge_page):
    assert merge_page.scrollable, "la seccion tiene una sola barra de desplazamiento"
    assert not hasattr(merge_page.list_frame, "_parent_canvas"), "la lista no tiene barra propia"


def test_preview_and_merge_with_watermark(merge_page, gui_app, tmp_path):
    assert not hasattr(merge_page, "add_signature"), "para firmar se usa Unir y firmar (seccion Firmar)"
    merge_page.refresh_preview()
    assert merge_page.preview.image is not None, "con archivos se ve la primera pagina"
    merge_page.add_watermark.select()
    merge_page._on_finish_toggled(log=False)
    merge_page.watermark.mark_text.set("BORRADOR")
    merge_page.go_to_preview_page(-1)
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
        assert not any(page.get_image_info() for page in document), "sin firma"


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


def test_preview_walks_through_every_page_of_the_result(merge_page, gui_app):
    assert merge_page.preview_total == 5
    merge_page.go_to_preview_page(0)
    merge_page.refresh_preview()
    assert merge_page.preview_label.cget("text") == "Página 1 de 5"
    assert merge_page.preview_source.cget("text").startswith("a.pdf")
    for _ in range(2):
        merge_page.step_preview(1)
    merge_page.refresh_preview()
    assert merge_page.preview_label.cget("text") == "Página 3 de 5"
    assert merge_page.preview_source.cget("text") == "b.pdf  ·  página 1", "la tercera es la primera de b.pdf"
    merge_page.go_to_preview_page(-1)
    merge_page.refresh_preview()
    assert merge_page.preview_next.cget("state") == "disabled"


def test_merge_and_sign_opens_the_result_in_sign(merge_page, gui_app, tmp_path):
    output = tmp_path / "para_firmar.pdf"
    merge_page.output_field.set(output)
    merge_page._merge_and_sign()
    pump(gui_app, lambda: output.exists() and not gui_app.runner.busy, timeout=10)
    pump(gui_app, lambda: gui_app.current_page == "Firmar", timeout=2)
    assert gui_app.current_page == "Firmar"
    assert gui_app.pages["Firmar"].source_field.path == output
    gui_app.show_page("Unir")


def test_viewer_merge_button_sends_open_documents(gui_app, tmp_path):
    gui_app.show_page("Visor")
    viewer = gui_app.pages["Visor"]
    try:
        assert viewer.open_file(make_pdf(tmp_path / "uno.pdf", 2))
        assert not viewer.merge_open_button.winfo_ismapped(), "con un solo documento no aparece"
        assert viewer.open_file(make_pdf(tmp_path / "dos.pdf", 1))
        pump(gui_app, timeout=0.1)
        assert viewer.merge_open_button.winfo_ismapped() and viewer.merge_open_button.cget("text") == "Unir 2 PDFs"
        viewer.tabs[0].session.rotate([0], 90)  # cambio sin guardar: va como copia con el cambio
        viewer.merge_open_documents()
        merge = gui_app.pages["Unir"]
        assert gui_app.current_page == "Unir"
        paths = merge.files
        assert len(paths) == 2 and paths[1] == tmp_path / "dos.pdf"
        assert paths[0] != tmp_path / "uno.pdf" and paths[0].exists(), "copia temporal con el cambio"
        with pymupdf.open(paths[0]) as copy:
            assert copy[0].rotation == 90
        assert viewer.tabs[0].session.modified, "el documento sigue sin guardar en el Visor"
    finally:
        viewer.close_all_documents()
        gui_app.pages["Unir"]._clear()
    assert viewer._exported_folder is not None
    viewer.forget_exported_copies()
