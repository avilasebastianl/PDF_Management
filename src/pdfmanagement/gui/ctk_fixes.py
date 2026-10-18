"""
Ajustes de rendimiento sobre CustomTkinter (sin modificar la libreria).

``CTkScrollbar._draw`` termina con ``update_idletasks()``: obliga a Tk a
maquetar y pintar *toda* la ventana cada vez que una barra de desplazamiento
cambia. Durante un cambio de tamano (pantalla completa, menu lateral) eso pasa
decenas de veces y se llevaba mas de un segundo, con la ventana congelada. Sin
esa llamada la barra se pinta en el siguiente ciclo, como cualquier widget.
"""

import customtkinter as ctk

_applied = False


def apply() -> None:
    """Aplica los ajustes una sola vez por proceso."""
    global _applied
    if _applied:
        return
    _applied = True
    original_draw = ctk.CTkScrollbar._draw  # noqa: SLF001

    def draw_without_flush(self, no_color_updates: bool = False) -> None:
        canvas = self._canvas
        if "update_idletasks" not in vars(canvas):
            canvas.update_idletasks = _no_op  # solo el lienzo de la barra
        original_draw(self, no_color_updates)

    ctk.CTkScrollbar._draw = draw_without_flush  # noqa: SLF001


def _no_op() -> None:
    return
