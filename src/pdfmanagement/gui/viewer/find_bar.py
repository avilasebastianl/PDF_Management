"""
Barra de busqueda flotante sobre el visor, como la de los navegadores.

Se abre con el boton "Buscar" o Ctrl+F y comparte el motor (y el texto
buscado) con el panel lateral ``SearchPanel``, que sigue mostrando la lista
completa de resultados. Enter busca o va al siguiente, Mayus+Enter al
anterior y Esc la cierra.
"""

from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from .. import style
from ..widgets import ToolTip, icon_button, muted_label, set_enabled
from .panels import SearchPanel


class FindBar(ctk.CTkFrame):
    def __init__(
        self, master, search: SearchPanel, *, on_show_list: Callable[[], None], on_close: Callable[[], None]
    ) -> None:
        super().__init__(
            master, corner_radius=10, fg_color=style.CARD_BG, border_width=1, border_color=style.CARD_BORDER
        )
        self.search = search
        self.visible = False
        self.entry = ctk.CTkEntry(
            self,
            textvariable=search.query,
            placeholder_text="Buscar en el documento",
            width=210,
            height=30,
            border_width=1,
        )
        self.entry.pack(side="left", padx=(8, 6), pady=6)
        self.entry.bind("<Return>", lambda _e: self._enter())
        self.entry.bind("<Shift-Return>", lambda _e: search.previous())
        self.entry.bind("<Escape>", lambda _e: on_close())
        self.count = muted_label(self, "", width=78, anchor="e")
        self.count.pack(side="left", padx=(0, 4))
        self.previous_button = icon_button(self, "up", search.previous, "Anterior (Mayus+Enter o Mayus+F3)", size=28)
        self.previous_button.pack(side="left")
        self.next_button = icon_button(self, "down", search.next, "Siguiente (Enter o F3)", size=28)
        self.next_button.pack(side="left")
        self.case_button = self._toggle("Aa", search.match_case, "Distinguir mayusculas y minusculas")
        self.words_button = self._toggle("ab", search.whole_words, "Solo palabras completas")
        list_button = icon_button(self, "list", on_show_list, "Ver todos los resultados en el panel lateral", size=28)
        list_button.pack(side="left", padx=(4, 0))
        close = icon_button(self, "clear", on_close, "Cerrar la busqueda (Esc)", size=28)
        close.pack(side="left", padx=(0, 6))
        search.add_listener(self.refresh)
        self.refresh()

    def _toggle(self, text: str, variable, tip: str) -> ctk.CTkButton:
        button = ctk.CTkButton(
            self,
            text=text,
            width=30,
            height=28,
            corner_radius=6,
            font=style.fonts().small,
            fg_color="transparent",
            hover_color=style.HOVER,
            text_color=style.TEXT,
        )
        button.configure(command=lambda: self._flip(variable, button))
        button.pack(side="left", padx=(2, 0))
        ToolTip(button, tip)
        return button

    def _flip(self, variable, button: ctk.CTkButton) -> None:
        variable.set(not variable.get())
        on = variable.get()
        button.configure(
            fg_color=style.accent_color() if on else "transparent", text_color=style.WHITE if on else style.TEXT
        )
        if self.search.query.get().strip():
            self.search.start()

    def _enter(self) -> None:
        if " ".join(self.search.query.get().split()) != self.search.searched_query:
            self.search.start()
        else:
            self.search.next()

    def show(self) -> None:
        if not self.visible:
            self.visible = True
            self.place(relx=1.0, x=-28, y=10, anchor="ne")
            self.lift()
            self.update_idletasks()  # Tk ignora el foco en una ventana aun no mapeada
        self.entry.focus_set()
        self.entry.select_range(0, "end")

    def hide(self) -> None:
        if self.visible:
            self.visible = False
            self.place_forget()

    def refresh(self) -> None:
        search = self.search
        if search.searching:
            text = "Buscando..."
        elif search.hits:
            text = f"{search.current + 1} de {len(search.hits)}" if search.current >= 0 else f"{len(search.hits)}"
        elif search.searched_query:
            text = "Sin resultados"
        else:
            text = ""
        if self.count.cget("text") != text:
            self.count.configure(text=text)
        set_enabled(self.previous_button, len(search.hits) > 1)
        set_enabled(self.next_button, len(search.hits) > 1)
