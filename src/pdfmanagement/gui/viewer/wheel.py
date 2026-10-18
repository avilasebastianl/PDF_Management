"""
Rueda del raton y panel tactil.

Tk 9 entrega la rueda al widget que esta bajo el cursor (no al que tiene el
foco). Las ruedas normales mandan ``<MouseWheel>`` de a 120 por muesca; los
paneles tactiles y las ruedas de alta resolucion mandan ``<TouchpadScroll>``
con pasos pequenos (15, 30...). Antes estos ultimos no se atendian y el visor
no se movia. ``WheelSteps`` convierte ambos en pasos enteros, acumulando las
fracciones, para que el desplazamiento sea proporcional y suave.
"""

from __future__ import annotations

WHEEL_NOTCH = 120  # unidades de Windows por muesca de la rueda
UNITS_PER_NOTCH = 3  # pasos de desplazamiento por muesca


def precise_deltas(widget, delta: int) -> tuple[int, int]:
    """``(dx, dy)`` de un ``<TouchpadScroll>`` (Tk los empaqueta en ``delta``)."""
    try:
        dx, dy = (int(value) for value in widget.tk.splitlist(widget.tk.call("tk::PreciseScrollDeltas", delta)))
    except Exception:  # Tk sin la funcion: se desempaqueta a mano
        dx, dy = (delta >> 16) & 0xFFFF, delta & 0xFFFF
        dx, dy = (value - 0x10000 if value >= 0x8000 else value for value in (dx, dy))
    return dx, dy


class WheelSteps:
    """Acumula la rueda y el panel tactil y devuelve pasos enteros (positivo = hacia abajo/derecha)."""

    def __init__(self) -> None:
        self._rest = {"x": 0.0, "y": 0.0, "zoom": 0.0}

    def wheel(self, delta: int) -> int:
        """Pasos verticales de un ``<MouseWheel>``."""
        return self._take("y", -delta / WHEEL_NOTCH * UNITS_PER_NOTCH)

    def touchpad(self, widget, delta: int) -> tuple[int, int]:
        """Pasos ``(horizontal, vertical)`` de un ``<TouchpadScroll>``."""
        dx, dy = precise_deltas(widget, delta)
        return (
            self._take("x", -dx / WHEEL_NOTCH * UNITS_PER_NOTCH),
            self._take("y", -dy / WHEEL_NOTCH * UNITS_PER_NOTCH),
        )

    def zoom(self, delta: int) -> int:
        """Muescas de zoom (Ctrl + rueda): positivo = acercar."""
        return self._take("zoom", delta / WHEEL_NOTCH)

    def _take(self, axis: str, amount: float) -> int:
        total = self._rest[axis] + amount
        steps = int(total)  # hacia cero: lo que sobra queda para el proximo evento
        self._rest[axis] = total - steps
        return steps
