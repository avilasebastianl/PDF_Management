"""
Barra de navegacion y zoom para un ``PageView``.
"""

import tkinter as tk

import customtkinter as ctk

from .. import style
from ..dropdown import dropdown_menu
from ..widgets import icon_button, set_enabled
from .page_view import FIT_PAGE, FIT_WIDTH, PageView

ZOOM_OPTIONS = {
    "Ajustar ancho": FIT_WIDTH,
    "Ajustar pagina": FIT_PAGE,
    **{f"{step}%": step for step in (50, 75, 100, 125, 150, 200, 300, 400)},
}


class ViewerToolbar(ctk.CTkFrame):
    """
    ``|<  <  [ 3 ] de 12  >  >|   -  [125% v]  +``

    Con ``page_entry=False`` muestra "Pagina 3 de 12" en lugar del campo.
    """

    def __init__(self, master, view: PageView, *, page_entry: bool = True, zoom_menu: bool = True) -> None:
        super().__init__(master, fg_color="transparent")
        self.view = view
        self.page_var = tk.StringVar()

        navigation = ctk.CTkFrame(self, fg_color="transparent")
        navigation.pack(side="left")
        self.first = icon_button(navigation, "first", lambda: view.go_to(0), "Primera pagina (Inicio)")
        self.previous = icon_button(navigation, "previous", lambda: view.go_to(view.current_page - 1), "Pagina anterior (RePag)")
        self.first.pack(side="left", padx=1)
        self.previous.pack(side="left", padx=1)
        if page_entry:
            entry = ctk.CTkEntry(navigation, textvariable=self.page_var, width=48, height=28, justify="center")
            entry.pack(side="left", padx=(6, 4))
            entry.bind("<Return>", self._go_to_typed)
            entry.bind("<FocusOut>", lambda _e: self._sync())
            self.total = ctk.CTkLabel(navigation, text="", font=style.fonts().body, width=50, anchor="w")
            self.total.pack(side="left", padx=(0, 4))
            self.page_label = None
        else:
            self.page_label = ctk.CTkLabel(navigation, text="", width=118, font=style.fonts().body)
            self.page_label.pack(side="left", padx=2)
            self.total = None
        self.next = icon_button(navigation, "next", lambda: view.go_to(view.current_page + 1), "Pagina siguiente (AvPag)")
        self.last = icon_button(navigation, "last", lambda: view.go_to(view.page_count - 1), "Ultima pagina (Fin)")
        self.next.pack(side="left", padx=1)
        self.last.pack(side="left", padx=1)

        zoom = ctk.CTkFrame(self, fg_color="transparent")
        zoom.pack(side="right")
        self.zoom_out = icon_button(zoom, "zoom_out", view.zoom_out, "Alejar (Ctrl + rueda)")
        self.zoom_out.pack(side="left", padx=1)
        if zoom_menu:
            self.zoom_menu = dropdown_menu(zoom, list(ZOOM_OPTIONS), self._choose_zoom, width=128, height=28)
            self.zoom_menu.pack(side="left", padx=4)
            self.zoom_label = None
        else:
            self.zoom_menu = None
            self.zoom_label = ctk.CTkLabel(zoom, text="", width=52, font=style.fonts().body)
            self.zoom_label.pack(side="left")
        self.zoom_in = icon_button(zoom, "zoom_in", view.zoom_in, "Acercar (Ctrl + rueda)")
        self.zoom_in.pack(side="left", padx=1)
        self.fit = icon_button(zoom, "fit", lambda: view.set_zoom(FIT_PAGE), "Ajustar pagina a la ventana")
        self.fit.pack(side="left", padx=(4, 0))

        # Espacio libre entre navegacion y zoom (p. ej. el nombre del documento en Firmar).
        self.center = ctk.CTkLabel(self, text="", font=style.fonts().small, text_color=style.TEXT_MUTED)
        self.center.pack(side="left", fill="x", expand=True, padx=12)

        self._last_state: tuple | None = None
        view.on_page_changed(lambda _page: self._sync())
        view.on_layout_changed(self._sync)
        self._sync()

    def _go_to_typed(self, _event=None) -> None:
        try:
            self.view.go_to(int(self.page_var.get()) - 1)
        except ValueError:
            pass
        self._sync()

    def _choose_zoom(self, label: str) -> None:
        self.view.set_zoom(ZOOM_OPTIONS[label])

    def _sync(self) -> None:
        view = self.view
        has_document = view.page_count > 0
        page, count = view.current_page, view.page_count
        state = (has_document, page, count, view.zoom_percent, view.zoom_mode)
        if state == self._last_state:  # cada configure de CustomTkinter redibuja: solo si cambio algo
            return
        self._last_state = state
        if self.page_label is not None:
            self.page_label.configure(text=f"Pagina {page + 1} de {count}" if has_document else "Sin documento")
        else:
            self.page_var.set(str(page + 1) if has_document else "")
            self.total.configure(text=f"de {count}" if has_document else "")
        set_enabled(self.first, has_document and page > 0)
        set_enabled(self.previous, has_document and page > 0)
        set_enabled(self.next, has_document and page < count - 1)
        set_enabled(self.last, has_document and page < count - 1)
        set_enabled(self.zoom_out, has_document)
        set_enabled(self.zoom_in, has_document)
        set_enabled(self.fit, has_document)
        text = f"{view.zoom_percent}%" if has_document else "—"
        if self.zoom_menu is not None:
            mode = view.zoom_mode
            label = next((name for name, value in ZOOM_OPTIONS.items() if value == mode and isinstance(mode, str)), text)
            if self.zoom_menu.get() != label:
                self.zoom_menu.set(label)
            menu_state = "normal" if has_document else "disabled"
            if self.zoom_menu.cget("state") != menu_state:
                self.zoom_menu.configure(state=menu_state)
        else:
            self.zoom_label.configure(text=text)
