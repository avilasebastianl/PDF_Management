"""
Listas desplegables con desplazamiento.

Envoltorio de ``_vendor.ctk_scrollable_dropdown`` (sin modificar el original)
que lo adapta a la aplicacion:

- Se crea al primer clic: el original llama a ``update()`` al construirse, lo
  que durante la precarga de paginas podia procesar eventos a mitad de la
  construccion.
- Aparece al instante (sin el fundido que bloqueaba la interfaz ~100 ms) y sin
  mostrar la barra de titulo la primera vez.
- Alto exacto para ``max_visible`` opciones (como mucho ``MAX_VISIBLE`` = 5);
  la barra de desplazamiento, con colores visibles, aparece si hay mas. Mide lo mismo que el control con cualquier escala de
  interfaz y se abre hacia arriba si no cabe debajo.
- Resalta la opcion actual y se desplaza hasta ella.
- Colores de la aplicacion en modo claro y oscuro.

Uso::

    menu = dropdown_menu(parent, values, command=on_change)
    set_dropdown_values(menu, nuevos_valores)
"""

import time
from collections.abc import Callable, Sequence

import customtkinter as ctk

from .._vendor.ctk_scrollable_dropdown import CTkScrollableDropdown
from . import style
from .events import area_of, debug_event
from .widgets import hide, show

ROW_HEIGHT = 30        # alto de cada opcion (pixeles logicos)
ROW_SPACING = 4        # el original separa cada opcion con pady=2
FRAME_PADDING = 14     # borde y margen interno del marco desplazable
MAX_VISIBLE = 5        # opciones visibles como maximo; las demas, con la barra
SCROLLBAR = ("gray58", "gray45")  # barra de la lista: visible sobre el fondo de la tarjeta
SCROLLBAR_HOVER = ("gray45", "gray60")
SELECTED = ("gray85", "gray30")
OPEN_GRACE_SECONDS = 0.2  # el clic que abre la lista no debe cerrarla


class _ScrollablePopup(CTkScrollableDropdown):
    """Ajustes de comportamiento sobre la lista vendorizada."""

    def __init__(self, attach, max_visible: int, **kwargs) -> None:
        self.max_visible = min(max_visible, MAX_VISIBLE)
        self._opened_at = 0.0
        root = attach.winfo_toplevel()
        configure_bindings = root.bind("<Configure>")
        super().__init__(attach, **kwargs)
        # El original cierra la lista ante cualquier <Configure> de la ventana, y
        # en Tk ese enlace recibe los de todos sus widgets: se cerraba sola con
        # cualquier reacomodo (cambio de seccion, barra de estado...). Se restaura
        # lo que habia y se cierra solo si la ventana principal se mueve o cambia.
        root.bind("<Configure>", configure_bindings)
        root.bind("<Configure>", self._on_root_configure, add="+")
        # El original activa overrideredirect tras 100 ms; sin esto la primera
        # apertura muestra un instante la barra de titulo.
        self.overrideredirect(True)
        self.bind("<<Opened>>", lambda _event: self._highlight_current(), add="+")

    def _withdraw(self) -> None:
        """
        Cierra la lista (clic fuera, Escape, ventana movida). El original solo
        cerraba si su bandera ``hide`` estaba activa, que al abrir queda en
        ``False``: el clic fuera nunca cerraba. Se ignora el mismo clic que la
        acaba de abrir, que tambien llega a la ventana principal.
        """
        if not self.winfo_exists() or time.monotonic() - self._opened_at < OPEN_GRACE_SECONDS:
            return
        if self.winfo_viewable():
            self.withdraw()
        self.event_generate("<<Closed>>")
        self.hide = True

    def _on_root_configure(self, event) -> None:
        # Al cerrar la ventana el control ancla se destruye antes que la raiz,
        # que sigue enviando <Configure>: sin esta guarda cada evento fallaba.
        if not (self.winfo_exists() and self.attach.winfo_exists()):
            return
        if event.widget is self.attach.winfo_toplevel() and self.winfo_viewable():
            self._withdraw()

    def fade_in(self) -> None:  # aparicion inmediata
        self.attributes("-alpha", self.alpha)

    def fade_out(self) -> None:  # cierre inmediato
        return

    def place_dropdown(self) -> None:
        attach = self.attach
        widget_scaling = ctk.ScalingTracker.get_widget_scaling(attach)
        window_scaling = ctk.ScalingTracker.get_window_scaling(self)
        rows = max(1, min(len(self.values), self.max_visible))
        # Alto fisico necesario; geometry() vuelve a escalar ancho y alto, la posicion no.
        physical_height = (rows * (ROW_HEIGHT + ROW_SPACING) + FRAME_PADDING) * widget_scaling
        width = attach.winfo_width() / window_scaling
        height = physical_height / window_scaling

        x = attach.winfo_rootx()
        y = attach.winfo_rooty() + attach.winfo_height() + 4
        if y + physical_height > attach.winfo_screenheight() - 48:
            y = attach.winfo_rooty() - physical_height - 4  # no cabe debajo: se abre hacia arriba

        scrollbar = self.frame._scrollbar  # noqa: SLF001
        (show if len(self.values) > self.max_visible else hide)(scrollbar)
        self.geometry(f"{round(width)}x{round(height)}+{x}+{round(y)}")
        self._opened_at = time.monotonic()
        self.attributes("-alpha", self.alpha)
        attach.focus()

    def _highlight_current(self) -> None:
        current = self.attach.get()
        index = 0
        for position, button in enumerate(self.widgets.values()):
            selected = button.cget("text") == current
            button.configure(fg_color=SELECTED if selected else self.button_color)
            if selected:
                index = position
        if len(self.values) > self.max_visible:
            self.frame._parent_canvas.yview_moveto(max(0.0, (index - 1) / len(self.values)))  # noqa: SLF001
        else:
            self.frame._parent_canvas.yview_moveto(0.0)  # noqa: SLF001


class _DropdownController:
    """Conecta un ``CTkOptionMenu`` con su lista desplazable (creada al primer clic)."""

    def __init__(self, menu: ctk.CTkOptionMenu, values: Sequence[str], command, max_visible: int) -> None:
        self.menu = menu
        self.values = list(values)
        self.command = command
        self.max_visible = min(max_visible, MAX_VISIBLE)
        self.popup: _ScrollablePopup | None = None
        # Reemplaza el menu nativo de CTkOptionMenu por la lista desplazable.
        for widget in (menu._canvas, menu._text_label):  # noqa: SLF001
            widget.bind("<Button-1>", self._first_open)

    def _first_open(self, _event=None) -> None:
        if self.menu.cget("state") == "disabled":
            return
        debug_event(area_of(self.menu), "Desplegable abierto", valor=self.menu.get(), opciones=len(self.values))
        if self.popup is None or not self.popup.winfo_exists():
            self.popup = _ScrollablePopup(
                self.menu,
                max_visible=self.max_visible,
                values=list(self.values),
                command=self._select,
                button_height=ROW_HEIGHT,
                height=_list_height(min(len(self.values), self.max_visible)),
                scrollbar=True,
                scrollbar_button_color=SCROLLBAR,
                scrollbar_button_hover_color=SCROLLBAR_HOVER,
                justify="left",
                resize=False,
                alpha=1.0,
                frame_corner_radius=8,
                frame_border_width=1,
                fg_color=style.CARD_BG,
                button_color=style.CARD_BG,
                hover_color=style.HOVER,
                text_color=style.TEXT,
                frame_border_color=style.CARD_BORDER,
                font=style.fonts().body,
                corner_radius=6,
            )
            # El original deja ``hide=False`` al construirse, por lo que su primer
            # _iconify solo "ocultaria" la lista; se marca oculta para abrirla ya.
            # Los clics siguientes los atiende su propio _iconify (ya enlazado).
            self.popup.hide = True
        self.popup._iconify()  # noqa: SLF001

    def _select(self, value: str) -> None:
        debug_event(area_of(self.menu), "Desplegable: elegido %s", value, anterior=self.menu.get())
        self.menu.set(value)
        if self.command:
            self.command(value)

    def set_values(self, values: Sequence[str]) -> None:
        self.values = list(values)
        self.menu.configure(values=self.values)
        if self.popup is not None and self.popup.winfo_exists():
            self.popup.configure(values=list(self.values), font=style.fonts().body, corner_radius=6)


def dropdown_menu(
    parent,
    values: Sequence[str],
    command: Callable[[str], None] | None = None,
    *,
    max_visible: int = MAX_VISIBLE,
    width: int = 180,
    **kwargs,
) -> ctk.CTkOptionMenu:
    """
    ``CTkOptionMenu`` cuya lista es desplazable y muestra hasta ``max_visible``
    opciones (nunca mas de ``MAX_VISIBLE``). ``command`` recibe el valor elegido.
    """
    menu = ctk.CTkOptionMenu(
        parent, values=list(values), width=width, dynamic_resizing=False, font=style.fonts().body, **kwargs
    )
    menu._dropdown = _DropdownController(menu, values, command, max_visible)  # noqa: SLF001
    return menu


def _list_height(rows: int) -> int:
    """Alto logico de la lista para ``rows`` opciones (el parametro ``height`` del original)."""
    return max(1, rows) * (ROW_HEIGHT + ROW_SPACING) + FRAME_PADDING


def set_dropdown_values(menu: ctk.CTkOptionMenu, values: Sequence[str]) -> None:
    """Actualiza las opciones de un menu creado con ``dropdown_menu``."""
    menu._dropdown.set_values(values)  # noqa: SLF001
