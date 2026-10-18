"""
Visor: dos paginas, modo nocturno, comparar documentos, imprimir, panel de
firmas y herramientas que cambian el contenido (reemplazar, texto fijo,
imagen, tapar). Requiere pantalla.
"""

import pymupdf
import pytest
from conftest import CERTIFICATE_PASSWORD, make_pdf, pump
from PIL import Image

from pdfmanagement import core
from pdfmanagement.core.verify import UNTRUSTED
from pdfmanagement.gui.pages import viewer as viewer_page
from pdfmanagement.gui.pages import viewer_annotations, viewer_display


class Event:
    def __init__(self, view, page, x, y):
        cx, cy = view.page_to_canvas(page, x, y)
        self.x = int(cx - view.canvas.canvasx(0))
        self.y = int(cy - view.canvas.canvasy(0))
        self.state = 0
        self.x_root = self.y_root = 0


def gesture(viewer, points, page=0):
    view = viewer.view
    view._dispatch("press", Event(view, page, *points[0]))
    for point in points[1:]:
        view._dispatch("drag", Event(view, page, *point))
    view._dispatch("release", Event(view, page, *points[-1]))


@pytest.fixture
def viewer(gui_app, tmp_path):
    gui_app.show_page("Visor")
    page = gui_app.pages["Visor"]
    assert page.open_file(make_pdf(tmp_path / "contrato.pdf", 5))
    page.view.set_zoom(100)
    pump(gui_app, timeout=0.3)
    yield page
    page.clear_marks()
    page.close_all_documents()
    page.set_two_pages(False)
    page.set_night_mode(False)


def text_of(viewer, page=0):
    return viewer.session.document[page].get_text()


# * Lectura -----------------------------------------------------------------------


def test_two_pages_side_by_side(viewer, gui_app):
    view = viewer.view
    viewer.set_two_pages(True)
    assert gui_app.settings.viewer_two_pages, "queda como preferencia al iniciar"
    first, second, third = view.layout[0], view.layout[1], view.layout[2]
    assert first[1] == second[1] and second[0] > first[2], "1 y 2 en la misma fila"
    assert third[1] > first[3], "3 empieza la fila siguiente"
    center = ((second[0] + second[2]) / 2, (second[1] + second[3]) / 2)
    assert view.canvas_to_page(*center).page == 1
    assert view.row_pages(3) == range(2, 4) and view.row_pages(4) == range(4, 5)
    view.go_to(3)
    pump(gui_app, timeout=0.1)
    assert 3 in view.visible_pages()
    viewer.set_two_pages(False)
    assert view.layout[1][1] > view.layout[0][3], "de nuevo en columna"


def test_night_mode_inverts_pages(viewer, gui_app):
    view = viewer.view
    viewer.set_night_mode(True)
    assert view.inverted and gui_app.settings.viewer_night_mode
    pump(gui_app, lambda: view.scheduler.get(0, view.scale) is not None, timeout=2)
    photo = view.scheduler.get(0, view.scale)
    corner = gui_app.root.tk.splitlist(gui_app.root.tk.call(str(photo), "get", 3, 3))
    assert [int(value) for value in corner] == [0, 0, 0], "el papel blanco se ve negro"
    viewer.set_night_mode(False)
    assert not view.inverted


def test_compare_with_another_tab(viewer, gui_app, tmp_path):
    assert viewer.open_file(make_pdf(tmp_path / "version2.pdf", 3))
    viewer.compare_with(0)
    pump(gui_app, timeout=0.2)
    compare = viewer.compare
    assert viewer.compare_tab is viewer.tabs[0] and compare.winfo_manager() == "grid"
    assert compare.view.page_count == 5
    viewer.view.go_to(2)
    pump(gui_app, timeout=0.1)
    assert compare.view.current_page == 2, "con Sincronizar pasan de pagina juntas"
    viewer.tabs[0].session.rotate([0], 90)  # editar el documento comparado lo actualiza
    pump(gui_app, timeout=0.1)
    assert compare.view.sizes[0] == (842, 595)
    viewer.close_tab(0, confirm=False)
    assert viewer.compare_tab is None and not compare.winfo_ismapped()


def test_print_uses_the_document_in_memory(viewer, monkeypatch):
    calls = []

    def fake_print(document, title, owner, progress):
        calls.append((document, title))
        progress(1, 2)
        return 2

    monkeypatch.setattr(viewer_display.printing, "print_document", fake_print)
    viewer.print_document()
    assert calls == [(viewer.session.document, "contrato.pdf")]
    assert "2" in viewer.selection_label.cget("text")
    monkeypatch.setattr(viewer_display.printing, "print_document", lambda *args: None)
    viewer.print_document()  # cancelado: sin error ni mensaje nuevo


# * Firmas --------------------------------------------------------------------------


def test_signatures_panel(viewer, gui_app, tmp_path, certificate):
    viewer.side_tabs.set(viewer_page.SIGNATURES_TAB)
    viewer._show_side(viewer_page.SIGNATURES_TAB)
    assert viewer.signatures.reports == [] and "no tiene firmas" in viewer.signatures.status.cget("text")
    signed = core.sign_pdf_with_certificate(
        make_pdf(tmp_path / "a.pdf", 1), tmp_path / "firmado.pdf", certificate[0], CERTIFICATE_PASSWORD
    )
    assert viewer.open_file(signed)
    pump(gui_app, lambda: bool(viewer.signatures.reports), timeout=5)
    [report] = viewer.signatures.reports
    assert report.state == UNTRUSTED
    sent = []
    monkeypatch_send = viewer._send_to
    viewer._send_to = sent.append
    try:
        viewer.signatures.sign_button.invoke()
    finally:
        viewer._send_to = monkeypatch_send
    assert sent == ["Firmar"]


# * Contenido de la pagina --------------------------------------------------------


def test_replace_selected_text(viewer, monkeypatch):
    viewer.text_tool.select_all(viewer.view, 0)
    viewer.annotations.select_tool("replace_text")
    editor = viewer.annotations.editor
    assert editor.value() == "Pagina 1", "el campo aparece sobre el texto, con el texto actual"
    editor.commit("Hola mundo")
    assert "Hola mundo" in text_of(viewer) and "Pagina 1" not in text_of(viewer)
    assert viewer.session.history.undo_label == "Reemplazar texto (página 1)"
    assert any(word[4] == "Hola" for word in viewer.session.words(0)), "el texto nuevo se puede seleccionar"
    viewer.undo()
    assert "Pagina 1" in text_of(viewer)


def test_redact_and_fixed_text(viewer, monkeypatch):
    viewer.annotations.select_tool("redact")
    gesture(viewer, [(60, 40), (320, 90)])
    assert "Pagina 1" not in text_of(viewer), "tapar elimina el texto de verdad"
    viewer.annotations.select_tool("fixed_text")
    gesture(viewer, [(100, 300)])
    viewer.annotations.editor.commit("Aprobado")
    assert "Aprobado" in text_of(viewer)
    assert viewer.session.history.undo_label == "Agregar texto fijo (página 1)"


def test_insert_image(viewer, monkeypatch, tmp_path):
    image = tmp_path / "sello.png"
    Image.new("RGB", (40, 30), "red").save(image)
    monkeypatch.setattr(viewer_annotations.filedialog, "askopenfilename", lambda **kwargs: str(image))
    viewer.annotations.select_tool("image")
    gesture(viewer, [(100, 200), (300, 350)])
    page = viewer.session.document[0]
    assert len(page.get_images()) == 1
    [info] = page.get_image_info()
    assert pymupdf.Rect(98, 198, 302, 352).contains(pymupdf.Rect(info["bbox"]))


# * Seleccionar elementos ------------------------------------------------------------


def test_select_tool_is_active_when_editing_and_finds_elements(viewer, tmp_path):
    viewer.toggle_edit_mode()
    assert viewer.annotations.active == "select", "al pulsar Editar se puede elegir enseguida"
    gesture(viewer, [(80, 66)])  # sobre "Pagina 1"
    element = viewer.annotations.element
    assert element is not None and element.element.kind == "text" and element.element.text == "Pagina 1"
    assert "Supr" in viewer.selection_label.cget("text")
    viewer._on_delete_key()
    assert "Pagina 1" not in text_of(viewer), "Supr elimina la linea seleccionada"
    assert viewer.session.history.undo_label == "Eliminar texto (página 1)"
    viewer.undo()
    viewer.toggle_edit_mode()


def test_double_click_edits_a_line_on_the_page(viewer):
    viewer.annotations.select_tool("select")
    view = viewer.view
    view._dispatch("double", Event(view, 0, 80, 66))
    editor = viewer.annotations.editor
    assert editor is not None and editor.value() == "Pagina 1"
    editor.commit("Portada")
    assert "Portada" in text_of(viewer)


def test_select_and_remove_an_image(viewer, monkeypatch, tmp_path):
    image = tmp_path / "logo.png"
    Image.new("RGB", (60, 40), "blue").save(image)
    monkeypatch.setattr(viewer_annotations.filedialog, "askopenfilename", lambda **kwargs: str(image))
    viewer.annotations.select_tool("image")
    gesture(viewer, [(200, 300), (320, 380)])
    assert len(viewer.session.document[0].get_images()) == 1
    viewer.annotations.select_tool("select")
    gesture(viewer, [(260, 340)])
    assert viewer.annotations.element.element.kind == "image"
    viewer._on_delete_key()
    assert viewer.session.document[0].get_image_info() == [], "la imagen se quito de la pagina"
    assert "Pagina 1" in text_of(viewer), "el texto no se toca"


def test_select_tool_picks_annotations_first(viewer):
    session = viewer.session
    session.add_shape(0, "rect", pymupdf.Rect(60, 50, 200, 90), viewer.annotations.style())
    viewer.annotations.reset()
    viewer.annotations.select_tool("select")
    gesture(viewer, [(61, 70)])
    assert viewer.annotations.selected is not None and viewer.annotations.element is None
