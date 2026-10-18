"""
Version 5.1: Nuevo PDF, menus con el estilo de la aplicacion, tamano de la
interfaz temporal y fundidos. Requiere pantalla.
"""

import tkinter as tk

import pytest
from conftest import make_pdf, pump

from pdfmanagement.core.create import NewDocument
from pdfmanagement.gui import new_document
from pdfmanagement.gui.pages import viewer_files
from pdfmanagement.gui.popup_menu import PopupMenu


@pytest.fixture
def viewer(gui_app):
    gui_app.show_page("Visor")
    page = gui_app.pages["Visor"]
    yield page
    page.close_all_documents()


def test_new_document_opens_in_a_temporary_tab(viewer, gui_app, monkeypatch):
    monkeypatch.setattr(viewer_files, "ask_new_document", lambda parent: NewDocument("invoice", "A4", False, 1))
    recents = list(viewer._recent)
    assert viewer.empty_actions.winfo_manager() == "place", "sin documento se ven los botones Abrir y Nuevo"
    viewer.new_document()
    tab = viewer.tab
    assert tab is not None and tab.temp_folder is not None and tab.session.path.exists()
    assert tab.session.path.parent == tab.temp_folder
    assert viewer._recent == recents, "un documento nuevo no va a Recientes"
    assert not viewer.empty_actions.winfo_manager()
    folder = tab.temp_folder
    viewer.close_tab(viewer.active, confirm=False)
    assert not folder.exists(), "al cerrar se borra su carpeta temporal"


def test_new_document_suggests_the_output_folder(viewer, gui_app, monkeypatch, tmp_path):
    monkeypatch.setattr(viewer_files, "ask_new_document", lambda parent: NewDocument("blank", "A4", False, 2))
    viewer.new_document()
    suggested = {}

    def fake_dialog(**options):
        suggested.update(options)
        return ""

    monkeypatch.setattr(viewer_files.filedialog, "asksaveasfilename", fake_dialog)
    viewer.save_as()
    assert suggested["initialdir"] == str(gui_app.settings.output_path)
    assert suggested["initialfile"] == viewer.session.path.name


def test_new_document_dialog(viewer, gui_app):
    dialog = new_document.NewDocumentDialog(viewer)
    pump(gui_app, timeout=0.2)
    dialog.select("minutes")
    assert dialog.pages_entry.cget("state") == "disabled", "las plantillas de formulario son de una pagina"
    dialog.select("lined")
    dialog.pages.set("4")
    dialog.orientation.set(new_document.ORIENTATIONS[1])
    dialog._accept()
    assert dialog.result == NewDocument("lined", "A4", True, 4)


def test_new_document_dialog_validates_pages(viewer, gui_app):
    dialog = new_document.NewDocumentDialog(viewer)
    dialog.pages.set("cero")
    dialog._accept()
    assert dialog.result is None and dialog.error.cget("text")
    dialog.destroy()


def test_popup_menu_items_and_checks(viewer, gui_app):
    called = []
    flag = tk.BooleanVar(value=False)
    menu = PopupMenu(viewer)
    menu.add_command(label="Uno", command=lambda: called.append(1), accelerator="Ctrl+1")
    menu.add_checkbutton(label="Opción", variable=flag)
    menu.add_separator()
    sub = PopupMenu(viewer)
    sub.add_command(label="Dentro", command=lambda: called.append(2))
    menu.add_cascade(label="Más", menu=sub)
    menu.add_command(label="Apagada", command=lambda: called.append(3), state="disabled")
    menu.tk_popup(viewer.winfo_rootx() + 40, viewer.winfo_rooty() + 40)
    pump(gui_app, timeout=0.1)
    assert menu.is_open and menu.labels() == ["Uno", "Opción", "Más", "Apagada"]
    menu.invoke("Opción")
    assert flag.get() and not menu.is_open, "elegir cierra el menu"
    menu.invoke("Apagada")
    sub.invoke("Dentro")
    menu.invoke("Uno")
    assert called == [2, 1]


def test_view_menu_uses_the_app_style(viewer, gui_app, tmp_path):
    assert viewer.open_file(make_pdf(tmp_path / "doc.pdf", 2))
    viewer.show_view_menu()
    menu = PopupMenu._active
    assert menu is not None and "Modo nocturno" in menu.labels()
    menu.invoke("Modo nocturno")
    assert viewer.view.inverted
    viewer.set_night_mode(False)


def test_temporary_interface_size_is_not_saved(gui_app):
    saved = gui_app.settings.ui_scaling
    gui_app.preview_ui_scaling(1.1)
    try:
        assert gui_app.ui_scaling == 1.1 and gui_app.settings.ui_scaling == saved
        assert "110" in gui_app.scaling_label.cget("text")
    finally:
        gui_app.preview_ui_scaling(saved)
    assert gui_app.ui_scaling == saved


def test_minus_and_plus_change_the_size_after_a_pause(gui_app):
    saved = gui_app.settings.ui_scaling
    gui_app.step_ui_scaling(1)
    gui_app.step_ui_scaling(1)
    assert gui_app.ui_scaling == saved, "aun no se aplica: se espera a que deje de pulsar"
    assert "125" in gui_app.scaling_label.cget("text")
    gui_app._apply_pending_scaling()
    try:
        assert gui_app.ui_scaling == 1.25 and gui_app.settings.ui_scaling == saved
    finally:
        gui_app.preview_ui_scaling(saved)
    for _ in range(10):
        gui_app.step_ui_scaling(-1)
    assert gui_app.scaling_minus.cget("state") == "disabled", "en el minimo, - queda desactivado"
    gui_app._apply_pending_scaling()
    gui_app.preview_ui_scaling(saved)
