"""
Seccion Visor y componente PageView: apertura, navegacion virtualizada,
miniaturas, marcadores, busqueda, seleccion y copia, zoom por mosaicos, envio
a otras secciones y organizacion de paginas (fase 2).

Requiere una pantalla (se omite si Tk no puede crear ventanas).
"""

import pymupdf
import pytest

from conftest import CERTIFICATE_PASSWORD, make_pdf, pump
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
    page.close_all_documents()  # sin preguntar por cambios sin guardar en la siguiente prueba


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
    # Antes leer needs_pass tras autenticar dejaba el documento en blanco.
    assert page.session.words(0)[0][4] == "Capitulo"


def test_shortcuts_only_work_in_the_viewer(gui_app, viewer):
    gui_app.show_page("Unir")
    viewer.side_tabs.set("Paginas")
    viewer._show_side("Paginas", log=False)
    event = type("E", (), {"keysym": "f"})()
    assert viewer._shortcut(event, viewer.open_search) is None
    assert not viewer.find_bar.visible
    gui_app.show_page("Visor")
    assert viewer._shortcut(event, viewer.open_search) == "break"
    assert viewer.find_bar.visible, "Ctrl+F abre la barra de busqueda flotante"
    viewer.close_find()


# * Organizar paginas (fase 2) ------------------------------------------------

def page_titles(viewer, count=None):
    """Primera linea de cada pagina: ``"Capitulo 1 - Seccion 3"``."""
    pages = range(viewer.session.page_count if count is None else count)
    return [" ".join(word[4] for word in viewer.session.words(index)[:5]) for index in pages]


def test_rotate_and_undo_update_the_whole_viewer(viewer, gui_app):
    assert viewer.rotate_pages(90)
    pump(gui_app, timeout=0.3)
    width, height = viewer.view.sizes[0]
    assert width > height, "la pagina girada se ve apaisada"
    assert viewer.session.modified and viewer.file_label.cget("text").endswith("•")
    assert viewer.undo_button.cget("state") == "normal"
    assert "Rotar pagina 1 a la derecha" in viewer._history_tip("Deshacer", "Ctrl+Z")
    viewer.undo()
    assert not viewer.session.modified and viewer.view.sizes[0][0] < viewer.view.sizes[0][1]
    assert viewer.redo_button.cget("state") == "normal"
    viewer.redo()
    assert viewer.session.document[0].rotation == 90


def test_drag_thumbnails_to_reorder(viewer, gui_app):
    viewer.set_edit_mode(True)  # fuera del modo edicion arrastrar no reordena
    strip = viewer.thumbnails
    strip.canvas.yview_moveto(0)
    pump(gui_app, timeout=0.2)

    def event(page, offset):
        y = strip._slots[page][1] - strip.canvas.canvasy(0) + offset
        return type("E", (), {"x": 60, "y": int(y), "state": 0})()

    strip._on_press(event(0, 10))
    strip._on_drag(event(0, 20))
    strip._on_drag(event(1, 150))  # mitad inferior de la miniatura 2: cae delante de la 3
    assert strip.dragging and strip._drop_target == 2
    strip._on_release(event(1, 150))
    pump(gui_app, timeout=0.2)
    assert page_titles(viewer, 3) == ["Capitulo 1 - Seccion 2", "Capitulo 1 - Seccion 1", "Capitulo 1 - Seccion 3"]
    assert strip.selection() == [1] and viewer.view.current_page == 1
    assert viewer.session.history.undo_label == "Mover pagina 1"
    viewer.undo()
    assert page_titles(viewer, 2) == ["Capitulo 1 - Seccion 1", "Capitulo 1 - Seccion 2"]
    viewer.set_edit_mode(False)


def test_multi_select_and_delete(viewer, gui_app, monkeypatch):
    from pdfmanagement.gui.pages import viewer as viewer_module

    strip = viewer.thumbnails
    strip._select_click(2, 0)
    strip._select_click(4, 0x0001)  # Mayus: 3 a 5
    strip._select_click(7, 0x0004)  # Ctrl: agrega la 8
    assert strip.selection() == [2, 3, 4, 7]
    assert viewer.pages_hint.cget("text") == "4 paginas seleccionadas"
    asked = []
    monkeypatch.setattr(viewer_module.messagebox, "askyesno", lambda *a, **k: asked.append(a) or True)
    viewer.delete_pages()
    assert asked, "eliminar varias paginas pide confirmacion"
    assert viewer.session.page_count == 36
    assert page_titles(viewer, 4)[2:] == ["Capitulo 1 - Seccion 6", "Capitulo 1 - Seccion 7"]
    assert len(strip._slots) == 36 and strip.selection() == [2]


def test_insert_pdf_and_blank_page(viewer, gui_app, tmp_path, monkeypatch):
    from pdfmanagement.gui.pages import viewer as viewer_module

    other = core.lock_pdf(make_pdf(tmp_path / "anexo.pdf", 2), tmp_path / "anexo_protegido.pdf", "clave")
    monkeypatch.setattr(viewer_module, "ask_password", lambda *a, **k: "clave")
    viewer.thumbnails._select_click(0, 0)
    assert viewer.insert_pdf_file(other)  # despues de la seleccion
    assert page_titles(viewer, 4)[1:3] == ["Pagina 1", "Pagina 2"]
    assert viewer.thumbnails.selection() == [1, 2] and viewer.session.page_count == 42
    assert viewer.insert_blank()
    assert viewer.session.words(3) == [] and viewer.session.page_count == 43
    # Los marcadores siguen apuntando a sus paginas (Capitulo 2 era la 11; ahora hay 3 antes).
    assert [page for _level, _title, page in viewer.outline.entries] == [1, 14, 24, 34]


def test_save_as_and_unsaved_changes_prompts(viewer, gui_app, tmp_path, manual_pdf, monkeypatch):
    from pdfmanagement.gui.pages import viewer as viewer_module

    viewer.rotate_pages(90)
    output = tmp_path / "manual_editado.pdf"
    assert viewer.save_to(output)
    assert not viewer.session.modified and viewer.saved_path == output
    assert viewer.file_label.cget("text") == "manual_editado.pdf"
    assert gui_app.status_bar.state == "success"
    with core.open_document(output) as saved:
        assert saved[0].rotation == 90
    errors = []
    monkeypatch.setattr(gui_app, "show_error", errors.append)  # sin dialogo modal
    assert not viewer.save_to(manual_pdf), "nunca sobre el original"
    assert isinstance(errors[0], core.InvalidInputError)

    viewer.rotate_pages(90)
    monkeypatch.setattr(viewer_module.messagebox, "askyesnocancel", lambda *a, **k: None)
    assert not viewer.close_current_tab() and viewer.session is not None, "Cancelar mantiene la pestana editada"
    assert viewer.session.modified
    closed = []
    monkeypatch.setattr(gui_app, "close", lambda *a, **k: closed.append(1))
    gui_app.request_close()
    assert not closed and gui_app.current_page == "Visor", "cerrar con cambios sin guardar se puede cancelar"
    monkeypatch.setattr(viewer_module.messagebox, "askyesnocancel", lambda *a, **k: False)
    assert viewer.close_tab(viewer.active), "No descarta los cambios y cierra la pestana"
    assert viewer.session is None and not viewer.tab_bar.winfo_manager()


def test_signed_document_warns_once_before_editing(gui_app, tmp_path, certificate, monkeypatch):
    from pdfmanagement.gui.pages import viewer as viewer_module

    signed = core.sign_pdf_with_certificate(make_pdf(tmp_path / "contrato.pdf", 2), tmp_path / "firmado.pdf",
                                            certificate[0], CERTIFICATE_PASSWORD)
    gui_app.show_page("Visor")
    page = gui_app.pages["Visor"]
    assert page.open_file(signed)
    answers = []
    monkeypatch.setattr(viewer_module.messagebox, "askyesno", lambda *a, **k: answers.append(1) or len(answers) > 1)
    assert not page.rotate_pages(90), "si no confirma, no se edita"
    assert not page.session.modified
    assert page.rotate_pages(90) and page.rotate_pages(90)
    assert len(answers) == 2, "se avisa hasta que confirma; despues no vuelve a preguntar"
    page._close_session()


def test_page_menu_and_editing_shortcuts(viewer, gui_app):
    viewer.thumbnails._select_click(1, 0)
    viewer.thumbnails._select_click(2, 0x0001)
    menu = viewer._page_menu()
    labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "command"]
    assert labels[:3] == ["Rotar 2 paginas a la derecha", "Rotar 2 paginas a la izquierda", "Eliminar 2 paginas"]
    menu.destroy()
    undo = type("E", (), {"keysym": "z"})()
    viewer.rotate_pages(-90)
    viewer.open_search()
    viewer.find_bar.entry._entry.focus_force()  # como si el usuario hiciera clic en el campo
    pump(gui_app, timeout=0.1)
    assert viewer._shortcut(undo, viewer.undo) is None, "Ctrl+Z dentro del campo de busqueda deshace el texto"
    viewer.view.canvas.focus_set()
    pump(gui_app, timeout=0.1)
    assert viewer._shortcut(undo, viewer.undo) == "break"
    assert not viewer.session.modified


def test_tabs_keep_each_document_and_its_view(viewer, gui_app, tmp_path):
    """Varios documentos a la vez, como pestanas de un navegador."""
    viewer.view.go_to(12)
    viewer.view.set_zoom(150)
    pump(gui_app, timeout=0.3)
    first = viewer.session
    other = make_pdf(tmp_path / "otro.pdf", 3)
    assert viewer.open_file(other)
    assert len(viewer.tabs) == 2 and viewer.active == 1 and viewer.session.page_count == 3
    assert [button.cget("text") for button in viewer._tab_buttons] == ["manual.pdf", "otro.pdf"]
    viewer.rotate_pages(90)  # cada pestana tiene su propio historial
    assert viewer._tab_buttons[1].cget("text") == "otro.pdf  •"
    viewer.switch_to(0)
    pump(gui_app, timeout=0.3)
    assert viewer.session is first and not first.modified
    assert viewer.view.current_page == 12 and viewer.view.zoom_percent == 150, "vuelve a donde estaba"
    assert viewer.open_file(other) and viewer.active == 1, "un archivo ya abierto muestra su pestana"
    viewer.cycle_tab(1)
    assert viewer.active == 0
    viewer.close_tab(1, confirm=False)
    assert len(viewer.tabs) == 1 and viewer.session is first


def test_fullscreen_hides_everything_but_the_viewer(viewer, gui_app):
    viewer.toggle_fullscreen()
    pump(gui_app, timeout=0.3)
    assert viewer.fullscreen and gui_app.root.attributes("-fullscreen")
    assert not gui_app.sidebar.winfo_ismapped() and not viewer.file_bar.winfo_ismapped()
    assert not viewer.side.winfo_ismapped() and viewer.view.winfo_ismapped()
    viewer.clear_marks()  # Esc
    pump(gui_app, timeout=0.3)
    assert not viewer.fullscreen and not gui_app.root.attributes("-fullscreen")
    assert gui_app.sidebar.winfo_ismapped() and viewer.file_bar.winfo_ismapped() and viewer.side.winfo_ismapped()
    viewer.toggle_fullscreen()
    gui_app.show_page("Unir")  # cambiar de seccion sale de pantalla completa
    pump(gui_app, timeout=0.3)
    assert not viewer.fullscreen and gui_app.sidebar.winfo_ismapped()
    gui_app.show_page("Visor")


def test_find_bar_searches_with_enter(viewer, gui_app):
    viewer.toggle_find()
    pump(gui_app, timeout=0.2)
    bar = viewer.find_bar
    assert bar.visible and bar.winfo_ismapped()
    viewer.search.query.set("vigencia")
    bar._enter()
    pump(gui_app, lambda: not viewer.search.searching)
    assert bar.count.cget("text") == f"1 de {len(viewer.search.hits)}"
    bar._enter()  # mismo texto: siguiente resultado
    assert bar.count.cget("text").startswith("2 de")
    bar._flip(viewer.search.match_case, bar.case_button)
    pump(gui_app, lambda: not viewer.search.searching)
    assert viewer.search.match_case.get() and bar.count.cget("text").startswith("1 de")
    bar._flip(viewer.search.match_case, bar.case_button)
    viewer.close_find()
    assert not bar.visible and viewer.search.hits == []


def test_window_mode_reads_in_the_whole_window(viewer, gui_app):
    viewer.toggle_window_mode()
    pump(gui_app, timeout=0.3)
    assert viewer.view_mode == "ventana" and not gui_app.root.attributes("-fullscreen"), "sin pantalla completa"
    assert not gui_app.sidebar.winfo_ismapped() and not viewer.file_bar.winfo_ismapped()
    assert not viewer.side.winfo_ismapped() and viewer.tab_bar.winfo_ismapped(), "las pestanas siguen a mano"
    assert gui_app.main.winfo_x() == 0 and gui_app.main.winfo_width() == gui_app.root.winfo_width()
    viewer.toggle_fullscreen()  # de un modo al otro directamente
    pump(gui_app, timeout=0.3)
    assert viewer.fullscreen and not viewer.tab_bar.winfo_ismapped()
    viewer.clear_marks()  # Esc
    pump(gui_app, timeout=0.3)
    assert viewer.view_mode == "normal" and gui_app.sidebar.winfo_ismapped() and viewer.side.winfo_ismapped()
    assert gui_app.main.winfo_x() == gui_app.sidebar.winfo_width()
