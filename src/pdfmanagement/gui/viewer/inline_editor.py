"""
Campo de texto sobre la pagina: escribir o editar texto en su lugar, sin
cuadros de dialogo (notas, cuadros de texto, texto fijo, reemplazar texto).

El campo se dibuja en el lienzo del visor con la letra al tamano real de la
pagina (con el zoom actual), asi lo que se escribe se ve donde va a quedar.
**Enter** aplica, **Mayus+Enter** agrega una linea, **Esc** cancela y hacer
clic fuera tambien aplica.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

import pymupdf

from ...i18n import tr
from .. import style
from .page_view import PageView

MIN_WIDTH_PX = 140
PADDING = 4
FONT = "Arial"  # se parece a Helvetica, la letra con la que se escribe en el PDF


class InlineEditor:
    """Un campo de texto activo sobre ``page`` en ``rect`` (puntos de la pagina visible)."""

    def __init__(
        self,
        view: PageView,
        page: int,
        rect: pymupdf.Rect,
        *,
        on_commit: Callable[[str], None],
        on_cancel: Callable[[], None] | None = None,
        initial: str = "",
        fontsize: float = 12.0,
        color: str = "#000000",
        background: str = "#FFFFFF",
    ) -> None:
        self.view = view
        self.page = page
        self.rect = pymupdf.Rect(rect)
        self.fontsize = fontsize
        self.on_commit = on_commit
        self.on_cancel = on_cancel
        self.initial = initial
        self.done = False
        canvas = view.canvas
        accent = style.themed(style.accent_color())
        self.frame = tk.Frame(canvas, background=accent, padx=2, pady=2)
        self.text = tk.Text(
            self.frame,
            height=1,
            wrap="word",
            undo=True,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=PADDING,
            pady=2,
            foreground=color,
            insertbackground=color,
            background=background,
            selectbackground=accent,
            selectforeground="white",
        )
        self.text.pack(fill="both", expand=True)
        self.hint = tk.Label(
            self.frame,
            text=tr("Enter: aplicar  ·  Esc: cancelar"),
            background=accent,
            foreground="white",
            font=(style.FONT_FAMILY, 8),
            anchor="w",
        )
        self.hint.pack(fill="x")
        self.text.insert("1.0", initial)
        self.text.tag_add("sel", "1.0", "end-1c")
        self.item: int | None = None
        self.text.bind("<Return>", self._on_return)
        self.text.bind("<KP_Enter>", self._on_return)
        self.text.bind("<Escape>", self._on_escape)
        self.text.bind("<KeyRelease>", lambda _e: self._fit_height(), add="+")
        self.text.bind("<FocusOut>", lambda _e: self.view.after(120, self._commit_if_unfocused), add="+")
        self.place()
        self.text.focus_set()

    # * Posicion y tamano -------------------------------------------------------------

    def place(self) -> None:
        """Ubica el campo sobre la pagina (tambien tras un cambio de zoom o de maqueta)."""
        view, canvas = self.view, self.view.canvas
        if self.done or not view.layout or self.page >= len(view.layout):
            return
        x0, y0 = view.page_to_canvas(self.page, self.rect.x0, self.rect.y0)
        x1, _y1 = view.page_to_canvas(self.page, self.rect.x1, self.rect.y1)
        font_px = max(9, round(self.fontsize * view.scale))
        self.text.configure(font=(FONT, -font_px))
        hint_width = self.hint.winfo_reqwidth() + 8  # que la ayuda de teclas se lea entera
        self._width = max(MIN_WIDTH_PX, hint_width, round(x1 - x0) + 2 * (PADDING + 2))
        if self.item is not None:
            canvas.delete(self.item)
        self.item = canvas.create_window(
            x0 - PADDING - 2, y0 - 4, anchor="nw", window=self.frame, width=self._width, tags=("editor",)
        )
        self._fit_height()

    def _fit_height(self) -> None:
        """Alto justo para las lineas escritas (crece al escribir, sin barra de desplazamiento)."""
        if self.done or self.item is None:
            return
        self.view.canvas.itemconfigure(self.item, width=self._width)
        self.text.update_idletasks()  # las lineas visibles dependen del ancho ya aplicado
        counted = self.text.count("1.0", "end", "displaylines")
        lines = max(1, int(counted[0])) if counted else 1
        if int(self.text.cget("height")) != lines:
            self.text.configure(height=lines)

    # * Aplicar o cancelar ------------------------------------------------------------

    def value(self) -> str:
        return self.text.get("1.0", "end-1c")

    def set_value(self, text: str) -> None:
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)

    def commit(self, text: str | None = None) -> None:
        """Aplica el texto (``text`` lo reemplaza antes; util para pruebas y atajos)."""
        if self.done:
            return
        if text is not None:
            self.set_value(text)
        value = self.value()
        self._close()
        if value.strip() and value != self.initial:
            self.on_commit(value)
        elif self.on_cancel is not None:
            self.on_cancel()

    def cancel(self) -> None:
        if self.done:
            return
        self._close()
        if self.on_cancel is not None:
            self.on_cancel()

    def _on_return(self, event) -> str:
        if event.state & 0x0001:  # Mayus+Enter: nueva linea
            self.text.insert("insert", "\n")
            self._fit_height()
        else:
            self.commit()
        return "break"

    def _on_escape(self, _event) -> str:
        self.cancel()
        return "break"

    def _commit_if_unfocused(self) -> None:
        if self.done:
            return
        try:
            focused = self.text.focus_get()
        except (KeyError, tk.TclError):
            focused = None
        if focused is None:
            return  # otra aplicacion paso al frente: se sigue editando al volver
        if focused not in (self.text, self.frame):
            self.commit()

    def _close(self) -> None:
        self.done = True
        if self.item is not None:
            self.view.canvas.delete(self.item)
            self.item = None
        self.frame.destroy()
        self.view.canvas.focus_set()
