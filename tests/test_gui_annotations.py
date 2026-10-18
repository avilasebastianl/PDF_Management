"""
Anotaciones en el Visor (fase 3) y menu lateral contraible.

Los gestos se simulan con eventos del lienzo en coordenadas de la pagina, como
los haria el raton. Requiere una pantalla (se omite si Tk no puede crear ventanas).
"""

import pytest
from conftest import make_pdf, pump


class Event:
    def __init__(self, view, page, x, y):
        cx, cy = view.page_to_canvas(page, x, y)
        self.x = int(cx - view.canvas.canvasx(0))
        self.y = int(cy - view.canvas.canvasy(0))
        self.state = 0
        self.x_root = self.y_root = 0


def gesture(viewer, points, page=0, double=False):
    view = viewer.view
    view._dispatch("press", Event(view, page, *points[0]))
    for point in points[1:]:
        view._dispatch("drag", Event(view, page, *point))
    view._dispatch("release", Event(view, page, *points[-1]))
    if double:
        view._dispatch("double", Event(view, page, *points[-1]))


@pytest.fixture
def viewer(gui_app, tmp_path):
    gui_app.show_page("Visor")
    page = gui_app.pages["Visor"]
    assert page.open_file(make_pdf(tmp_path / "contrato.pdf", 3))
    page.view.set_zoom(100)
    pump(gui_app, timeout=0.4)
    yield page
    page.clear_marks()
    page.close_all_documents()


def kinds(viewer, page=0):
    return [info.kind for info in viewer.session.annotations(page)]


def test_highlight_selected_text_with_one_click(viewer, gui_app):
    viewer.text_tool.select_all(viewer.view, 0)
    viewer.annotations.select_tool("highlight")
    assert kinds(viewer) == ["Highlight"]
    assert viewer.annotations.active is None, "con texto seleccionado no cambia de herramienta"
    assert viewer.session.history.undo_label == "Resaltar texto (página 1)"
    assert "Ctrl+Z" in viewer.selection_label.cget("text")


def test_markup_tool_drag_over_text(viewer):
    viewer.annotations.set_color("Rojo")
    viewer.annotations.select_tool("strikeout")
    assert viewer.annotations.tool_buttons["strikeout"].cget("fg_color") != "transparent"
    gesture(viewer, [(70, 65), (150, 70)])
    assert kinds(viewer) == ["StrikeOut"]
    assert viewer.session.annotations(0)[0].color == pytest.approx((0.9, 0.15, 0.15), abs=0.01)


def test_drag_shapes_lines_and_ink(viewer):
    annotations = viewer.annotations
    annotations.select_tool("rect")
    gesture(viewer, [(100, 200), (180, 250), (250, 300)])
    annotations.select_tool("arrow")
    gesture(viewer, [(100, 350), (300, 420)])
    annotations.select_tool("ink")
    gesture(viewer, [(100 + i * 8, 500 + (i % 3) * 6) for i in range(12)])
    annotations.select_tool("ellipse")
    gesture(viewer, [(300, 200), (301, 201)])  # un clic no dibuja nada
    assert kinds(viewer) == ["Square", "Line", "Ink"]
    assert "Arrastre" in viewer.selection_label.cget("text")
    viewer.undo()
    assert kinds(viewer) == ["Square", "Line"]


def write(viewer, text):
    """Escribe en el campo abierto sobre la pagina y lo aplica (como pulsar Enter)."""
    editor = viewer.annotations.editor
    assert editor is not None and not editor.done, "debe haber un campo de texto sobre la pagina"
    editor.commit(text)


def test_note_and_free_text_are_written_on_the_page(viewer):
    annotations = viewer.annotations
    annotations.select_tool("note")
    gesture(viewer, [(400, 100)])
    write(viewer, "Revisar")
    gesture(viewer, [(400, 200)])
    annotations.editor.cancel()  # Esc: no agrega nada
    annotations.select_tool("free_text")
    gesture(viewer, [(100, 600)])  # clic: cuadro de tamano estandar
    write(viewer, "APROBADO")
    infos = viewer.session.annotations(0)
    assert [(info.kind, info.content) for info in infos] == [("Text", "Revisar"), ("FreeText", "APROBADO")]
    assert infos[1].rect.width == pytest.approx(220, abs=2)


def test_select_move_edit_and_delete(viewer, monkeypatch):
    session = viewer.session
    annotations = viewer.annotations
    annotations.select_tool("rect")
    gesture(viewer, [(100, 200), (200, 260)])
    annotations.cancel_tool()
    assert viewer.view.tool is viewer.text_tool and viewer.tool_selector.get() == "Texto"
    before = session.annotations(0)[0].rect
    gesture(viewer, [(101, 230), (130, 250), (160, 270)])  # arrastrar el borde del rectangulo
    after = session.annotations(0)[0]
    assert after.rect.x0 == pytest.approx(before.x0 + 60, abs=2) and after.rect.y0 == pytest.approx(
        before.y0 + 40, abs=2
    )
    assert annotations.selected is not None and annotations.selected.xref == after.xref
    annotations.set_color("Verde")  # cambia el color de la seleccionada
    assert session.history.undo_label == "Cambiar color de rectángulo"
    viewer._on_delete_key()  # Supr: elimina la anotacion, no la pagina
    assert kinds(viewer) == [] and session.page_count == 3

    session.add_note(0, (300, 300), "viejo", annotations.style())
    annotations.reset()
    gesture(viewer, [(305, 305)], double=True)
    assert annotations.editor.value() == "viejo", "el campo trae el texto actual"
    write(viewer, "nuevo texto")
    assert session.annotations(0)[0].content == "nuevo texto"


def test_dragging_on_highlight_still_selects_text(viewer):
    viewer.text_tool.select_all(viewer.view, 0)
    viewer.annotations.select_tool("highlight")
    gesture(viewer, [(75, 65), (130, 68)])
    assert viewer.text_tool.selected_text(), "sobre un resaltado, arrastrar selecciona texto"
    assert viewer.annotations.selected is None


def test_annotations_panel_and_context_menu(viewer, gui_app, monkeypatch):
    session = viewer.session
    style = viewer.annotations.style()
    session.add_note(1, (100, 100), "en la segunda", style)
    session.add_shape(0, "ellipse", (100, 100, 200, 200), style)
    viewer.annotations.reset()
    viewer.side_tabs.set("Notas")
    viewer._show_side("Notas")
    pump(gui_app, timeout=0.2)
    panel = viewer.annotations.panel
    items = [panel.list.listbox.get(i) for i in range(panel.list.listbox.size())]
    assert items == ["p. 1  ·  Elipse", "p. 2  ·  Nota: en la segunda"]
    panel._selected(1)
    assert viewer.annotations.selected.content == "en la segunda" and viewer.view.current_page == 1
    assert panel.edit_button.cget("state") == "normal"
    viewer.annotations.edit_text()
    write(viewer, "editada")
    assert session.annotations(1)[0].content == "editada"
    assert panel.list.listbox.get(1) == "p. 2  ·  Nota: editada"
    menu = viewer._page_menu(from_view=True, annotation=viewer.annotations.selected)
    labels = menu.labels(("command", "cascade"))
    assert labels[:3] == ["Editar nota...", "Color", "Eliminar nota"]
    viewer.side_tabs.set("Páginas")
    viewer._show_side("Páginas", log=False)


def test_escape_ends_annotation_tool(viewer):
    viewer.annotations.select_tool("ink")
    assert viewer.view.tool is not viewer.text_tool
    viewer.clear_marks()
    assert viewer.annotations.active is None and viewer.view.tool is viewer.text_tool
    assert viewer.edit_mode, "elegir una herramienta activa el modo edicion"
    viewer.toggle_edit_mode()
    assert not viewer.edit_mode and viewer.annotations.bar.winfo_manager() == ""
    assert viewer.thumbnails.on_move is None, "fuera del modo edicion no se reordena arrastrando"
    viewer.toggle_edit_mode()
    assert viewer.edit_mode and viewer.edit_button.cget("text") in ("Listo", "")  # "" con la barra compacta
    viewer.set_edit_mode(False)


def test_sidebar_collapses_to_icons(gui_app):
    assert not gui_app.settings.sidebar_collapsed
    gui_app.toggle_sidebar()
    pump(gui_app, lambda: gui_app._sidebar_animation is None, timeout=0.3)
    assert gui_app.settings.sidebar_collapsed
    assert gui_app.sidebar.cget("width") == 64
    sidebar_width = gui_app.sidebar.winfo_width()
    assert gui_app.main.winfo_x() == sidebar_width, "el contenido queda justo a la derecha del menu"
    assert gui_app.main.winfo_width() == gui_app.root.winfo_width() - sidebar_width
    assert all(button.cget("text") == "" for button in gui_app.nav_buttons.values())
    assert not gui_app._brand.winfo_ismapped()
    # Contraido, el tooltip dice el nombre de la seccion.
    assert _tooltips(gui_app.nav_buttons["Firmar"]) == ["Firmar  (Ctrl+5)"]
    gui_app.toggle_sidebar()
    pump(gui_app, lambda: gui_app._sidebar_animation is None, timeout=0.3)
    assert gui_app.nav_buttons["Firmar"].cget("text") == "  Firmar"
    assert gui_app.sidebar.cget("width") == 220
    from pdfmanagement.gui.pages.registry import PAGES

    title = next(page.title for page in PAGES if page.name == "Firmar")
    assert _tooltips(gui_app.nav_buttons["Firmar"]) == [f"{title}  (Ctrl+5)"]


def _tooltips(widget):
    """Textos de los ToolTip enlazados al widget (se buscan entre los objetos vivos)."""
    import gc

    from pdfmanagement.gui.widgets import ToolTip

    found = [obj for obj in gc.get_objects() if isinstance(obj, ToolTip) and obj.widget is widget]
    return [tip.text() if callable(tip.text) else tip.text for tip in found]


def test_adding_text_keeps_the_scroll_position(viewer, gui_app, monkeypatch):
    """Antes, al agregar un texto el visor saltaba al principio de la pagina."""
    viewer.view.go_to(1)
    viewer.view._scroll_units(12)  # a mitad de la pagina 2
    pump(gui_app, timeout=0.3)
    before = viewer.view.canvas.yview()[0]
    viewer.annotations.select_tool("free_text")
    gesture(viewer, [(100, 300)], page=1)
    write(viewer, "Comentario")
    pump(gui_app, timeout=0.3)
    assert [info.content for info in viewer.session.annotations(1)] == ["Comentario"]
    assert viewer.view.canvas.yview()[0] == pytest.approx(before, abs=1e-6)


def test_font_size_menu_changes_selected_text(viewer, monkeypatch):
    annotations = viewer.annotations
    annotations._set_font_size("18")  # tamano para el texto nuevo
    annotations.select_tool("free_text")
    gesture(viewer, [(100, 200)])
    write(viewer, "Titulo")
    info = viewer.session.annotations(0)[0]
    assert info.font_size == 18
    annotations.cancel_tool()
    gesture(viewer, [(info.rect.x0 + 5, info.rect.y0 + 5)])  # seleccionarlo
    assert annotations.selected is not None and annotations.size_menu.get() == "18"
    annotations._set_font_size("32")
    assert viewer.session.annotations(0)[0].font_size == 32
    assert viewer.session.history.undo_label == "Cambiar tamaño de texto"
