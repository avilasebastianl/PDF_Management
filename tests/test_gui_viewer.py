"""
Seccion Visor y componente PageView: apertura, navegacion virtualizada,
miniaturas, marcadores, busqueda, seleccion y copia, zoom por mosaicos y envio
a otras secciones.

Requiere una pantalla (se omite si Tk no puede crear ventanas).
"""

import pymupdf
import pytest

from conftest import pump
from pdfmanagement import core


@pytest.fixture(scope="module")
def manual_pdf(tmp_path_factory):
    path = tmp_path_factory.mktemp("visor") / "manual.pdf"
    document = pymupdf.open()
    toc = []
    for index in range(40):
        page = document.new_page()
        page.insert_text((60, 70), f"Capitulo {index // 10 + 1} - Seccion {index + 1}", fontsize=18)
        page.insert_textbox(pymupdf.Rect(60, 100, 540, 760),
                            "El contrato de servicios establece la vigencia del acuerdo entre las partes. " * 8,
                            fontsize=11)
        if index % 10 == 0:
            toc.append([1, f"Capitulo {index // 10 + 1}", index + 1])
    document.set_toc(toc)
    document.save(path)
    return path


@pytest.fixture
def viewer(gui_app, manual_pdf):
    gui_app.show_page("Visor")
    page = gui_app.pages["Visor"]
    assert page.open_file(manual_pdf)
    pump(gui_app, timeout=0.6)
    yield page
    page.clear_marks()


def test_open_shows_document_thumbnails_and_outline(viewer):
    assert viewer.session.page_count == 40
    assert viewer.view.page_count == 40
    assert len(viewer.thumbnails._slots) == 40
    assert [title for _level, title, _page in viewer.outline.entries] == [f"Capitulo {n}" for n in range(1, 5)]
    assert viewer.file_label.cget("text") == "manual.pdf"
    assert viewer.send_menu.cget("state") == "normal"


def test_only_visible_pages_are_rendered(viewer, gui_app):
    rendered_pages = {page for page, _tile in viewer.view._displayed}
    assert rendered_pages, "las paginas visibles deben dibujarse"
    assert len(rendered_pages) < 10, "un documento de 40 paginas no se dibuja entero"
    viewer.view.go_to(25)
    pump(gui_app, timeout=0.6)
    assert viewer.view.current_page == 25
    assert all(abs(page - 25) <= 5 for page, _tile in viewer.view._displayed)


def test_outline_and_thumbnails_navigate(viewer, gui_app):
    viewer.outline._go_to(2)  # "Capitulo 3" -> pagina 21
    pump(gui_app, timeout=0.2)
    assert viewer.view.current_page == 20
    assert viewer.toolbar.page_var.get() == "21"


def test_search_highlights_and_cycles_results(viewer, gui_app):
    viewer.open_search()
    viewer.search.query.set("vigencia")
    viewer.search.start()
    pump(gui_app, lambda: viewer.search._iterator is None)
    hits = viewer.search.hits
    assert len(hits) >= 40
    assert viewer.view.search_hits, "las coincidencias se resaltan en el visor"
    first = viewer.search.current
    viewer.search.next()
    assert viewer.search.current == first + 1
    viewer.search.previous()
    viewer.search.previous()
    assert viewer.search.current == len(hits) - 1, "anterior desde el primero va al ultimo"


def test_select_and_copy_text(viewer, gui_app):
    viewer.text_tool.select_all(viewer.view, viewer.view.current_page)
    viewer.copy_selection()
    copied = gui_app.root.clipboard_get()
    assert copied.startswith("Capitulo")
    assert "contrato de servicios" in copied


def test_zoom_uses_tiles_and_fit_modes(viewer, gui_app):
    viewer.view.set_zoom(400)
    pump(gui_app, timeout=0.8)
    assert viewer.view.zoom_percent == 400
    tiles = [tile for _page, tile in viewer.view._displayed if tile is not None]
    assert tiles, "con zoom alto se dibujan mosaicos, no la pagina entera"
    viewer.view.set_zoom("fit_width")
    pump(gui_app, timeout=0.4)
    assert viewer.view.zoom_mode == "fit_width"
    assert all(tile is None for _page, tile in viewer.view._displayed)


def test_send_to_other_sections(viewer, gui_app, manual_pdf):
    viewer._send_to("Unir")
    pump(gui_app, timeout=0.4)
    assert gui_app.current_page == "Unir"
    assert manual_pdf.resolve() in gui_app.pages["Unir"].files
    gui_app.pages["Unir"]._clear()
    gui_app.show_page("Visor")


def test_protected_pdf_asks_for_password(gui_app, manual_pdf, tmp_path, monkeypatch):
    from pdfmanagement.gui.pages import viewer as viewer_module

    locked = core.lock_pdf(manual_pdf, tmp_path / "protegido.pdf", "clave123")
    answers = iter(["mala", "clave123"])
    monkeypatch.setattr(viewer_module, "ask_password", lambda *args, **kwargs: next(answers))
    gui_app.show_page("Visor")
    page = gui_app.pages["Visor"]
    assert page.open_file(locked)
    assert page.session.encrypted and page.session.page_count == 40


def test_shortcuts_only_work_in_the_viewer(gui_app, viewer):
    gui_app.show_page("Unir")
    viewer.side_tabs.set("Miniaturas")
    viewer._show_side("Miniaturas", log=False)
    event = type("E", (), {"keysym": "f"})()
    assert viewer._shortcut(event, viewer.open_search) is None
    assert viewer.side_tabs.get() == "Miniaturas"
    gui_app.show_page("Visor")
    assert viewer._shortcut(event, viewer.open_search) == "break"
    assert viewer.side_tabs.get() == "Buscar"
