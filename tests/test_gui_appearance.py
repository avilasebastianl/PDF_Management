"""
Cambio de tema priorizado: lo visible se actualiza de inmediato, lo oculto por
lotes, y al final todos los widgets quedan con el modo correcto.

Requiere una pantalla (se omite si Tk no puede crear ventanas).
"""

import time

import customtkinter as ctk
import pytest


@pytest.fixture
def window(gui_app, pdf_factory):
    gui_app.set_appearance_mode("Dark")
    _pump(gui_app, lambda: not gui_app.appearance._pending)
    gui_app.show_page("Unir")
    for page in ("Extraer", "Convertir", "Firmar", "Proteger", "Ajustes"):
        gui_app._ensure_page(page)
    merge = gui_app.pages["Unir"]
    if len(merge.entries) < 15:
        merge._add_files([pdf_factory(f"doc_{index}.pdf", 1) for index in range(15)])
    _pump(gui_app, lambda: not merge._rows_to_build and not gui_app.runner.busy)
    return gui_app


def _pump(main, done, timeout=20.0):
    end = time.time() + timeout
    while not done() and time.time() < end:
        main.root.update()
        time.sleep(0.01)
    main.root.update()


def _widget_modes() -> set[int]:
    modes = set()
    for callback in ctk.AppearanceModeTracker.callback_list:
        widget = getattr(callback, "__self__", None)
        mode = getattr(widget, "_CTkAppearanceModeBaseClass__appearance_mode", None)
        if mode is not None:
            modes.add(mode)
    return modes


def test_theme_switch_prioritizes_visible_and_finishes_everything(window):
    window.set_appearance_mode("Light")
    pending = sum(len(group) for group in window.appearance._pending.values())
    assert pending > 0, "las secciones ocultas y filas fuera de vista deben diferirse"
    assert _widget_modes() == {0, 1}, "justo despues del cambio aun quedan widgets por actualizar"

    _pump(window, lambda: not window.appearance._pending)
    assert _widget_modes() == {0}, "al terminar, todos los widgets deben estar en modo claro"


def test_opening_a_pending_page_updates_it_first(window):
    window.set_appearance_mode("Light")
    sign_page = window.pages["Firmar"]
    assert id(sign_page) in window.appearance._pending
    window.show_page("Firmar")
    assert id(sign_page) not in window.appearance._pending


def test_quick_toggles_end_in_last_mode(window):
    for mode in ("Light", "Dark", "Light"):
        window.set_appearance_mode(mode)
        window.root.update_idletasks()
    _pump(window, lambda: not window.appearance._pending)
    assert _widget_modes() == {0}


def test_app_icon_variant_applies_at_once(gui_app):
    from pdfmanagement.gui import app_icon, style

    gui_app.show_page("Ajustes")
    page = gui_app.pages["Ajustes"]
    try:
        page._on_app_icon("negro")
        assert gui_app.settings.app_icon == "negro" and app_icon.current() == "negro"
        assert app_icon.ico_path().name == "app_negro.ico"
        assert page.icon_buttons["negro"].cget("border_color") == style.accent_color()
        assert page.icon_buttons["clasico"].cget("border_color") == style.CARD_BG
        assert str(page.about_logo.cget("image"))  # el logo de "Acerca de" cambia con la variante
    finally:
        page._on_app_icon("clasico")
    assert app_icon.current() == "clasico"
