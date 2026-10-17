"""
Cambio de tema priorizado: lo visible se actualiza de inmediato, lo oculto por
lotes, y al final todos los widgets quedan con el modo correcto.

Requiere una pantalla (se omite si Tk no puede crear ventanas).
"""

import time
import tkinter

import customtkinter as ctk
import pytest

from pdfmanagement import paths
from pdfmanagement.config import Settings


@pytest.fixture
def window(tmp_path, monkeypatch, pdf_factory):
    monkeypatch.setattr(paths, "LOG_DIR", tmp_path / "log")
    monkeypatch.setattr(paths, "SIGNATURES_DIR", tmp_path / "signs")
    try:
        from pdfmanagement.gui.app import MainWindow

        settings = Settings(appearance_mode="Dark", output_dir=str(tmp_path / "out"), open_after_save=False)
        main = MainWindow(settings)
    except tkinter.TclError as error:
        pytest.skip(f"Sin pantalla disponible: {error}")
    main.save_settings = lambda: None
    main.show_page("Unir")
    for page in ("Extraer", "Convertir", "Firmar", "Proteger", "Ajustes"):
        main._ensure_page(page)
    merge = main.pages["Unir"]
    merge._add_files([pdf_factory(f"doc_{index}.pdf", 1) for index in range(15)])
    _pump(main, lambda: not merge._rows_to_build and not main.runner.busy)
    yield main
    main.close(exit_process=False)


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
