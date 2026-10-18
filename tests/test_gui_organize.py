"""
Seccion Organizar: cuadricula de paginas para reordenar (arrastrando), girar,
eliminar e insertar. Requiere pantalla.
"""

import pytest
from conftest import make_pdf, page_texts, pump

from pdfmanagement.gui.pages import organize as organize_page


class Event:
    """Evento del lienzo en el centro de la tarjeta (o desplazado ``dx``)."""

    def __init__(self, grid, page, dx=0.0, dy=0.0, state=0):
        m = grid._metrics()
        x, y = grid._cells[page]
        cx, cy = x + m["card_w"] / 2 + dx, y + m["pad"] + m["box_h"] / 2 + dy
        self.x = int(cx - grid.canvas.canvasx(0))
        self.y = int(cy - grid.canvas.canvasy(0))
        self.state = state
        self.x_root = self.y_root = 0


@pytest.fixture
def organize(gui_app, tmp_path):
    gui_app.show_page("Organizar")
    page = gui_app.pages["Organizar"]
    assert page.open_file(make_pdf(tmp_path / "conjunto.pdf", 5))
    pump(gui_app, timeout=0.3)
    yield page
    if page.session is not None:
        page.session.history.mark_saved()  # sin preguntar por cambios al cerrar
    page._close_session()


def texts(page):
    # session.words y no get_text: este gira las paginas mientras lee (ver core/editing/engine.py).
    return [" ".join(word[4] for word in page.session.words(i)) for i in range(page.session.page_count)]


def test_section_is_registered(gui_app):
    assert "Organizar" in gui_app.nav_buttons


def test_select_with_click_ctrl_and_shift(organize):
    grid = organize.grid_view
    grid._on_press(Event(grid, 1))
    grid._on_release(Event(grid, 1))
    assert grid.selection() == [1]
    grid._on_press(Event(grid, 3, state=0x0004))  # Ctrl: agrega
    assert grid.selection() == [1, 3]
    grid._on_press(Event(grid, 4, state=0x0001))  # Mayus: rango desde la ultima elegida
    assert grid.selection() == [3, 4]
    assert organize.delete_button.cget("state") == "normal"


def test_drag_to_reorder(organize, gui_app):
    grid = organize.grid_view
    grid._on_press(Event(grid, 0))
    grid._on_drag(Event(grid, 2, dx=10))
    grid._on_drag(Event(grid, 3, dx=-grid._metrics()["card_w"] / 2 + 2))  # justo antes de la pagina 4
    assert grid._drop_index == 3 and grid.canvas.find_withtag("drop")
    grid._on_release(Event(grid, 3))
    assert texts(organize) == ["Pagina 2", "Pagina 3", "Pagina 1", "Pagina 4", "Pagina 5"]
    assert grid.selection() == [2], "la pagina movida sigue seleccionada"
    organize.undo()
    assert texts(organize)[0] == "Pagina 1"


def test_rotate_delete_and_insert(organize, monkeypatch):
    organize.rotate([0, 1], 90)
    assert [organize.session.document[i].rotation for i in (0, 1, 2)] == [90, 90, 0]
    organize.delete([4])
    assert organize.session.page_count == 4
    organize.insert_blank(0)
    assert organize.session.page_count == 5 and texts(organize)[0] == ""
    assert organize.grid_view.selection() == [0]
    assert organize.undo_button.cget("state") == "normal"


def test_plus_button_opens_the_insert_menu(organize, monkeypatch):
    opened = []
    monkeypatch.setattr(organize, "_show_insert_menu", lambda at, x, y: opened.append(at))
    organize.grid_view.on_insert = organize._show_insert_menu
    grid = organize.grid_view
    m = grid._metrics()
    grid._on_press(Event(grid, 2, dx=-(m["card_w"] + m["gap"]) / 2))  # el + antes de la pagina 3
    assert opened == [2]


def test_save_as_keeps_the_original(organize, gui_app, tmp_path, monkeypatch):
    organize.move([4], 0)
    output = tmp_path / "ordenado.pdf"
    monkeypatch.setattr(organize_page.filedialog, "asksaveasfilename", lambda **kwargs: str(output))
    assert organize.save_as()
    assert page_texts(output)[0] == "Pagina 5"
    assert page_texts(tmp_path / "conjunto.pdf")[0] == "Pagina 1", "el original no se toca"
    assert not organize.session.modified


def test_viewer_can_send_to_organize():
    from pdfmanagement.gui.pages import viewer_files

    assert "Organizar" in viewer_files.SEND_TARGETS.values()
