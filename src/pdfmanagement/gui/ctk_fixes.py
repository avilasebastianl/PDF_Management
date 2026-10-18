"""
Ajustes de rendimiento sobre CustomTkinter (sin modificar la libreria).

``CTkScrollbar._draw`` termina con ``update_idletasks()``: obliga a Tk a
maquetar y pintar *toda* la ventana cada vez que una barra de desplazamiento
cambia. Durante un cambio de tamano (pantalla completa, menu lateral) eso pasa
decenas de veces y se llevaba mas de un segundo, con la ventana congelada. Sin
esa llamada la barra se pinta en el siguiente ciclo, como cualquier widget.

``CTkScrollableFrame`` solo atiende ``<MouseWheel>``: con Tk 9 los paneles
tactiles mandan ``<TouchpadScroll>`` y las secciones no se desplazaban. Se
agrega ese evento con la misma velocidad que la rueda.
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

    original_init = ctk.CTkScrollableFrame.__init__

    def init_with_touchpad(self, *args, **kwargs) -> None:
        original_init(self, *args, **kwargs)
        self.bind_all("<TouchpadScroll>", lambda event: _touchpad_scroll(self, event), add="+")

    ctk.CTkScrollableFrame.__init__ = init_with_touchpad


def _touchpad_scroll(frame, event) -> None:
    """Desplaza la seccion bajo el cursor como lo haria la rueda (CTk: delta / 6 pasos)."""
    from .viewer.wheel import precise_deltas

    try:
        if not frame.winfo_exists() or not frame.check_if_master_is_canvas(event.widget):
            return
    except Exception:  # widget ya destruido
        return
    canvas = frame._parent_canvas  # noqa: SLF001
    _dx, dy = precise_deltas(canvas, event.delta)
    steps = -round(dy / 6)
    if steps and canvas.yview() != (0.0, 1.0):
        canvas.yview("scroll", steps, "units")


def _no_op() -> None:
    return
