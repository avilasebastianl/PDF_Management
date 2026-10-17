"""
Listas desplegables con desplazamiento (``gui/dropdown.py``).

Requiere una pantalla (se omite si Tk no puede crear ventanas).
"""

from PIL import Image, ImageDraw

from conftest import pump
from pdfmanagement import paths


def _open(menu, window):
    pump(window, timeout=0.3)  # la seccion recien mostrada termina de acomodarse
    menu._dropdown._first_open()
    pump(window, timeout=0.3)
    return menu._dropdown.popup


def test_short_list_shows_every_option_without_scrollbar(gui_app):
    gui_app.show_page("Ajustes")
    page = gui_app.pages["Ajustes"]
    chosen = []
    page.color._dropdown.command = chosen.append
    popup = _open(page.color, gui_app)
    try:
        assert popup.winfo_viewable(), "el primer clic debe abrir la lista"
        assert abs(popup.winfo_width() - page.color.winfo_width()) <= 2
        assert not popup.frame._scrollbar.winfo_ismapped()
        highlighted = [b.cget("text") for b in popup.widgets.values() if b.cget("fg_color") != popup.button_color]
        assert highlighted == [page.color.get()]
        popup._attach_key_press("Verde")
        pump(gui_app, timeout=0.2)
        assert page.color.get() == "Verde" and chosen == ["Verde"]
        assert not popup.winfo_viewable()
    finally:
        popup._withdraw()


def test_long_list_scrolls_after_six_options(gui_app):
    paths.SIGNATURES_DIR.mkdir(parents=True, exist_ok=True)
    for index in range(9):
        image = Image.new("RGBA", (120, 40), (0, 0, 0, 0))
        ImageDraw.Draw(image).line((5, 30, 115, 10), fill=(0, 0, 0, 255), width=4)
        image.save(paths.SIGNATURES_DIR / f"lista_{index}.png")
    gui_app.show_page("Firmar")
    page = gui_app.pages["Firmar"]
    page._refresh_signatures()
    popup = _open(page.signature_menu, gui_app)
    try:
        assert len(popup.values) > 6
        assert popup.frame._scrollbar.winfo_ismapped()
        row = popup.widgets[0].winfo_reqheight()
        assert popup.winfo_height() < row * 8, "debe mostrar unas 6 opciones, no la lista completa"
    finally:
        popup._withdraw()

    # Las opciones de la lista se actualizan al cambiar la biblioteca.
    (paths.SIGNATURES_DIR / "lista_0.png").unlink()
    page._refresh_signatures()
    assert "lista_0.png" not in page.signature_menu._dropdown.popup.values


def test_real_clicks_open_close_and_click_outside(gui_app):
    import time

    gui_app.show_page("Ajustes")
    page = gui_app.pages["Ajustes"]
    menu = page.scaling
    pump(gui_app, timeout=0.3)

    def click(widget):
        widget.event_generate("<ButtonPress-1>", x=5, y=5)
        widget.event_generate("<ButtonRelease-1>", x=5, y=5)
        pump(gui_app, timeout=0.15)

    click(menu._canvas)
    popup = menu._dropdown.popup
    assert popup.winfo_viewable(), "un clic en el control abre la lista y no la cierra en el acto"
    time.sleep(0.25)
    click(menu._canvas)
    assert not popup.winfo_viewable(), "otro clic en el control la cierra"

    click(menu._canvas)
    assert popup.winfo_viewable()
    time.sleep(0.25)
    click(page.output_dir._label)
    assert not popup.winfo_viewable(), "un clic fuera de la lista la cierra"


def test_destroyed_menu_ignores_window_events(gui_app):
    """Al cerrar la app los controles se destruyen antes que la raiz: no debe fallar."""
    import customtkinter as ctk

    from pdfmanagement.gui.dropdown import dropdown_menu

    holder = ctk.CTkFrame(gui_app.pages["Ajustes"])
    menu = dropdown_menu(holder, ["Uno", "Dos"])
    popup = _open(menu, gui_app)
    holder.destroy()
    event = type("E", (), {"widget": gui_app.root})()
    popup._on_root_configure(event)  # antes lanzaba TclError: bad window path name
    popup.destroy()
