"""
Visor de Firmar: redimensionado de la firma y acceso a la guia del certificado.

Requiere una pantalla (se omite si Tk no puede crear ventanas).
"""

import time

import pytest

from pdfmanagement import core


@pytest.fixture
def window(gui_app):
    gui_app.show_page("Firmar")
    return gui_app


@pytest.fixture
def sign_page(window, pdf_factory, signature_png):
    from pdfmanagement import signatures

    page = window.pages["Firmar"]
    page.mode.set("Firma visual")
    page._apply_mode()
    page._refresh_signatures(select=signatures.import_signature(signature_png, "firma"))
    page.source_field.set(pdf_factory("doc.pdf", 2))
    _pump(window)
    page._set_position(200, 300)
    _pump(window)
    return page


def _pump(window, seconds=0.3):
    end = time.time() + seconds
    while time.time() < end:
        window.root.update()
        time.sleep(0.01)


class _Event:
    def __init__(self, page, x, y):
        self.x = int(page.offset[0] + x * page.scale - page.canvas.canvasx(0))
        self.y = int(page.offset[1] + y * page.scale - page.canvas.canvasy(0))
        self.state = 0


def _drag(page, start, end):
    page._on_press(_Event(page, *start))
    page._on_drag(_Event(page, *end))
    page._on_release(None)


def test_dragging_a_corner_resizes_keeping_the_opposite_corner(sign_page):
    before = sign_page._current_rect()
    _drag(sign_page, (before.x1, before.y1), (before.x1 + 60, before.y1 + 10))
    after = sign_page._current_rect()
    assert after.width > before.width + 50
    assert after.x0 == pytest.approx(before.x0, abs=0.2)
    assert after.y0 == pytest.approx(before.y0, abs=0.2)
    assert after.height / after.width == pytest.approx(before.height / before.width, rel=0.01)

    _drag(sign_page, (after.x0, after.y0), (after.x0 + 80, after.y0 + 20))
    shrunk = sign_page._current_rect()
    assert shrunk.width < after.width
    assert shrunk.x1 == pytest.approx(after.x1, abs=0.2)
    assert shrunk.y1 == pytest.approx(after.y1, abs=0.2)


def test_size_controls_resize_from_the_center_and_stay_in_sync(sign_page):
    before = sign_page._current_rect()
    sign_page._step_size(10)
    after = sign_page._current_rect()
    assert after.width == pytest.approx(before.width + 10, abs=0.2)
    assert (after.x0 + after.x1) / 2 == pytest.approx((before.x0 + before.x1) / 2, abs=0.2)

    sign_page._on_size_slider(220)
    assert float(sign_page.width_var.get()) == pytest.approx(220, abs=0.2)
    sign_page.width_var.set("120")
    assert sign_page.size_slider.get() == pytest.approx(120, abs=0.5)


def test_signature_never_leaves_the_page(sign_page):
    sign_page._apply_size(10_000)
    rect = sign_page._current_rect()
    page = sign_page.page_rect
    assert rect.x0 >= 0 and rect.y0 >= 0
    assert rect.x1 <= page.width + 0.5 and rect.y1 <= page.height + 0.5


def test_resized_signature_matches_the_pdf(sign_page, tmp_path):
    import pymupdf

    sign_page._apply_size(180)
    rect = sign_page._current_rect()
    output = tmp_path / "firmado.pdf"
    core.sign_pdf_with_image(
        sign_page.document_path, output, sign_page.signature_paths[sign_page.signature_menu.get()],
        sign_page._placement(),
    )
    with pymupdf.open(output) as document:
        box = pymupdf.Rect(document[sign_page.page_index].get_image_info()[0]["bbox"])
    assert all(abs(a - b) < 1 for a, b in zip(box, rect))


def test_certificate_guide_link_opens_its_section(window):
    from pdfmanagement.gui.pages.sign import CERTIFICATE_GUIDE_SECTION

    window.open_help(CERTIFICATE_GUIDE_SECTION)
    _pump(window, 0.3)
    assert CERTIFICATE_GUIDE_SECTION in window._help._sections, "el titulo de la guia debe coincidir con el enlace"


# * Biblioteca de firmas y vista previa -----------------------------------------

def _preview_tk_image(page) -> str:
    """Imagen que muestra realmente la etiqueta Tk interna de la vista previa."""
    return str(page.signature_preview._label.cget("image"))


def test_choosing_no_signature_clears_the_preview(sign_page):
    assert _preview_tk_image(sign_page), "con una firma elegida debe verse su imagen"
    sign_page._select_signature(NO_SIGNATURE_LABEL)
    assert _preview_tk_image(sign_page) == ""
    assert sign_page.signature_preview.cget("text") == "Sin firma seleccionada"


def test_creating_importing_and_deleting_signatures_in_a_row(sign_page, signature_png, signature_jpg, tmp_path):
    import gc

    from pdfmanagement import signatures
    from pdfmanagement.gui.dialogs import SignaturePad

    window = sign_page.app
    # Dibujar una firma nueva con el lienzo (simulando trazos del mouse).
    pad = SignaturePad(sign_page, on_saved=lambda path: sign_page._refresh_signatures(select=path))
    _pump(window, 0.2)
    pad.name.set("nueva")
    pad.strokes = [[(40, 150, 3), (200, 120, 3), (420, 180, 3)]]
    pad._save()
    gc.collect()
    _pump(window, 0.2)
    assert sign_page.signature_menu.get().startswith("nueva")
    assert _preview_tk_image(sign_page)

    # Importar otra y volver a elegir: antes fallaba con 'image "pyimageN" does not exist'.
    sign_page._refresh_signatures(select=signatures.import_signature(signature_jpg, "escaneada"))
    gc.collect()
    sign_page._select_signature(NO_SIGNATURE_LABEL)
    sign_page._select_signature(sign_page.signature_menu.cget("values")[1])
    gc.collect()
    assert _preview_tk_image(sign_page)

    # Borrar la seleccionada.
    window_messagebox = __import__("tkinter").messagebox
    original = window_messagebox.askyesno
    window_messagebox.askyesno = lambda *args, **kwargs: True
    try:
        sign_page._delete_signature()
    finally:
        window_messagebox.askyesno = original
    gc.collect()
    _pump(window, 0.1)
    assert sign_page.signature_menu.get() in sign_page.signature_menu.cget("values")


NO_SIGNATURE_LABEL = "Sin firma"
