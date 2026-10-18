"""
Componentes reutilizables de la interfaz.
"""

import ctypes
import ctypes.wintypes
import sys
import tkinter as tk
from collections.abc import Callable, Iterable
from pathlib import Path
from tkinter import filedialog
from typing import ClassVar

import customtkinter as ctk
from tkinterdnd2 import DND_FILES

from ..i18n import tr
from . import style
from .events import area_of, debug_event, log_event
from .icons import icon

FileTypes = tuple[tuple[str, str], ...]
PDF_FILETYPES: FileTypes = ((tr("Archivos PDF"), "*.pdf"),)
LABEL_COLUMN_WIDTH = 170  # alinea los campos de todas las tarjetas


def format_size(size_bytes: int) -> str:
    """Tamano legible: ``532 B``, ``1.4 MB``."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def set_label_image(label: ctk.CTkLabel, image: ctk.CTkImage | None, text: str = "") -> None:
    """
    Cambia (o quita) la imagen de un ``CTkLabel`` de forma segura.

    CustomTkinter no borra la imagen al recibir ``image=None`` y, si la imagen
    anterior ya fue liberada, cualquier ``configure`` posterior falla con
    ``image "pyimageN" does not exist``. Por eso primero se desvincula la
    imagen del widget Tk interno y luego se asigna la nueva.

    Quien llama debe conservar una referencia a ``image`` mientras se muestre.
    """
    label._label.configure(image="")  # noqa: SLF001 - CTkLabel no expone su etiqueta Tk
    label.configure(image=image, text=text)


def hide(widget) -> None:
    """
    Oculta un widget ubicado con ``grid`` recordando sus opciones.

    CustomTkinter repite la ultima llamada a ``grid`` al cambiar la escala, lo
    que volveria a mostrar widgets ocultos con ``grid_remove``; por eso se
    olvida esa llamada y se guarda aparte para ``show``.
    """
    call = getattr(widget, "_last_geometry_manager_call", None)
    if call:
        widget._hidden_grid_kwargs = call["kwargs"]  # noqa: SLF001 - atributos propios de CustomTkinter
        widget._last_geometry_manager_call = None  # noqa: SLF001
    widget.grid_remove()


def show(widget) -> None:
    """Vuelve a mostrar un widget oculto con ``hide``."""
    widget.grid(**getattr(widget, "_hidden_grid_kwargs", {}))


# * Botones -----------------------------------------------------------------


def primary_button(parent, text: str, command: Callable, icon_name: str | None = None, **kwargs) -> ctk.CTkButton:
    """Boton de accion principal (color del tema)."""
    return ctk.CTkButton(
        parent,
        text=text,
        command=command,
        image=icon(icon_name, 16, style.ON_ACCENT) if icon_name else None,
        height=38,
        font=style.fonts().body_bold,
        corner_radius=8,
        **kwargs,
    )


def secondary_button(parent, text: str, command: Callable, icon_name: str | None = None, **kwargs) -> ctk.CTkButton:
    """Boton secundario con borde y fondo transparente."""
    return ctk.CTkButton(
        parent,
        text=text,
        command=command,
        image=icon(icon_name, 16) if icon_name else None,
        height=kwargs.pop("height", 34),
        fg_color=kwargs.pop("fg_color", "transparent"),
        hover_color=style.HOVER,
        border_width=1,
        border_color=style.CARD_BORDER,
        text_color=style.TEXT,
        font=style.fonts().body,
        corner_radius=8,
        **kwargs,
    )


def icon_button(
    parent, icon_name: str, command: Callable, tooltip: str | Callable[[], str], size: int = 32, **kwargs
) -> ctk.CTkButton:
    """
    Boton cuadrado solo con icono y tooltip (texto fijo o funcion que lo
    calcula al mostrarse). Use ``set_enabled`` para activarlo o no.
    """
    disabled = kwargs.get("state") == "disabled"
    button = ctk.CTkButton(
        parent,
        text="" if icon(icon_name) else (tooltip if isinstance(tooltip, str) else tooltip())[:1],
        image=icon(icon_name, 16, style.TEXT_DISABLED if disabled else style.TEXT),
        width=size,
        height=size,
        fg_color="transparent",
        hover_color=style.HOVER,
        text_color=style.TEXT,
        corner_radius=6,
        command=command,
        **kwargs,
    )
    ToolTip(button, tooltip)
    button.icon_key = icon_name
    return button


def set_enabled(button: ctk.CTkButton, enabled: bool) -> None:
    """Activa o desactiva un ``icon_button`` atenuando su icono cuando no esta disponible."""
    if (button.cget("state") == "normal") == enabled:
        return
    button.configure(
        state="normal" if enabled else "disabled",
        image=icon(button.icon_key, 16, style.TEXT if enabled else style.TEXT_DISABLED),
    )


# * Estructura --------------------------------------------------------------


class PageHeader(ctk.CTkFrame):
    """Titulo y descripcion de una pagina."""

    def __init__(self, parent, title: str, subtitle: str) -> None:
        super().__init__(parent, fg_color="transparent")
        ctk.CTkLabel(self, text=title, font=style.fonts().title, text_color=style.TEXT, anchor="w").pack(fill="x")
        ctk.CTkLabel(
            self, text=subtitle, font=style.fonts().subtitle, text_color=style.TEXT_MUTED, anchor="w", justify="left"
        ).pack(fill="x", pady=(2, 0))


class Card(ctk.CTkFrame):
    """
    Tarjeta con titulo opcional. El contenido se ubica con ``grid`` a partir de
    ``first_row``; la columna 1 se expande.
    """

    def __init__(self, parent, title: str | None = None, description: str | None = None, **kwargs) -> None:
        super().__init__(
            parent,
            corner_radius=style.CORNER,
            fg_color=style.CARD_BG,
            border_width=1,
            border_color=style.CARD_BORDER,
            **kwargs,
        )
        self.grid_columnconfigure(0, minsize=LABEL_COLUMN_WIDTH)
        self.grid_columnconfigure(1, weight=1)
        self.first_row = 0
        if title:
            ctk.CTkLabel(self, text=title, font=style.fonts().section, text_color=style.TEXT, anchor="w").grid(
                row=0, column=0, columnspan=4, sticky="ew", padx=style.CARD_PAD, pady=(style.CARD_PAD - 2, 0)
            )
            self.first_row = 1
        if description:
            ctk.CTkLabel(
                self,
                text=description,
                font=style.fonts().small,
                text_color=style.TEXT_MUTED,
                anchor="w",
                justify="left",
            ).grid(row=self.first_row, column=0, columnspan=4, sticky="ew", padx=style.CARD_PAD)
            self.first_row += 1
        # Espaciador inferior para que la ultima fila tenga margen.
        self._bottom = ctk.CTkFrame(self, width=1, height=style.CARD_PAD - 8, fg_color="transparent")
        self._bottom.grid(row=99, column=0, padx=(style.CARD_PAD, 0), pady=(0, 4))

    def row(self, offset: int) -> int:
        """Fila de grid para el elemento numero ``offset`` del contenido."""
        return self.first_row + offset


def field_label(parent, text: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(parent, text=text, font=style.fonts().body, text_color=style.TEXT, anchor="w")


def muted_label(parent, text: str = "", **kwargs) -> ctk.CTkLabel:
    options = {"anchor": "w", "justify": "left", **kwargs}
    return ctk.CTkLabel(parent, text=text, font=style.fonts().small, text_color=style.TEXT_MUTED, **options)


# * Campos ------------------------------------------------------------------


class FileField:
    """
    Campo de ruta con boton "Examinar" y soporte para arrastrar archivos.

    En modo ``save`` registra si el usuario confirmo la ruta en el dialogo del
    sistema (que ya pregunta por sobrescritura) o si fue generada
    automaticamente (``auto``), para decidir si hace falta confirmar.
    """

    def __init__(
        self,
        parent,
        row: int,
        label: str,
        *,
        mode: str = "open",
        filetypes: FileTypes = PDF_FILETYPES,
        on_change: Callable[[Path], None] | None = None,
        placeholder: str = "",
        initial_dir: Callable[[], Path] | None = None,
        stacked: bool = False,
    ) -> None:
        self.mode = mode
        self.label = label
        self.filetypes = filetypes
        self.on_change = on_change
        self.initial_dir = initial_dir
        self.variable = tk.StringVar()
        self.auto = False
        self.confirmed_path: Path | None = None
        self._setting = False
        self.variable.trace_add("write", self._on_typed)

        pad = style.CARD_PAD
        label_widget = field_label(parent, label)
        self.entry = ctk.CTkEntry(parent, textvariable=self.variable, placeholder_text=placeholder, height=34)
        self.button = secondary_button(parent, tr("Examinar"), self.browse, "folder", width=110)

        if stacked:
            label_widget.grid(row=row, column=0, columnspan=3, sticky="w", padx=pad, pady=(style.GAP, 2))
            self.entry.grid(row=row + 1, column=0, columnspan=2, sticky="ew", padx=(pad, 6))
            self.button.grid(row=row + 1, column=2, sticky="e", padx=(0, pad))
        else:
            label_widget.grid(row=row, column=0, sticky="w", padx=(pad, style.GAP), pady=style.GAP // 2 + 2)
            self.entry.grid(row=row, column=1, sticky="ew", pady=style.GAP // 2 + 2)
            self.button.grid(row=row, column=2, sticky="e", padx=(8, pad), pady=style.GAP // 2 + 2)

        self._widgets = (label_widget, self.entry, self.button)
        if mode == "open":
            enable_file_drop(self.entry, self._on_drop)

    def hide(self) -> None:
        for widget in self._widgets:
            hide(widget)

    def show(self) -> None:
        for widget in self._widgets:
            show(widget)

    @property
    def path(self) -> Path | None:
        value = self.variable.get().strip().strip('"')
        return Path(value) if value else None

    def get(self) -> str:
        return self.variable.get().strip().strip('"')

    def set(self, value: Path | str, *, auto: bool = False, notify: bool = True) -> None:
        self._setting = True
        self.variable.set(str(value))
        self._setting = False
        self.auto = auto
        self.confirmed_path = None
        if notify and self.on_change and value:
            self.on_change(Path(value))

    def browse(self) -> None:
        initial = self.initial_dir() if self.initial_dir else None
        current = self.path
        if current and current.parent.exists():
            initial = current.parent
        initialdir = str(initial) if initial else None
        if self.mode == "save":
            chosen = filedialog.asksaveasfilename(
                title=tr("Guardar como"),
                defaultextension=".pdf",
                initialfile=current.name if current else "",
                filetypes=self.filetypes,
                initialdir=initialdir,
            )
            if chosen:
                self._log_choice(Path(chosen), "Guardar como")
                self.set(Path(chosen))
                self.confirmed_path = Path(chosen)
            else:
                debug_event(area_of(self.entry), "%s: dialogo cancelado", self.label)
        else:
            chosen = filedialog.askopenfilename(
                title=tr("Seleccionar archivo"), filetypes=self.filetypes, initialdir=initialdir
            )
            if chosen:
                self._log_choice(Path(chosen), "dialogo")
                self.set(Path(chosen))
            else:
                debug_event(area_of(self.entry), "%s: dialogo cancelado", self.label)

    def _on_drop(self, files: list[Path]) -> None:
        if files:
            extra = f" (se usa el primero de {len(files)})" if len(files) > 1 else ""
            self._log_choice(files[0], f"arrastrado{extra}")
            self.set(files[0])

    def _log_choice(self, path: Path, origin: str) -> None:
        """Registra el archivo que el usuario eligio para este campo."""
        log_event(area_of(self.entry), "%s: %s", self.label, path, origen=origin)

    def _on_typed(self, *_args) -> None:
        if not self._setting:
            self.auto = False
            self.confirmed_path = None


class PasswordField:
    """Entrada de contrasena con boton para mostrar u ocultar el texto."""

    def __init__(self, parent, row: int, label: str, placeholder: str = "") -> None:
        self.variable = tk.StringVar()
        pad = style.CARD_PAD
        self.entry = ctk.CTkEntry(parent, textvariable=self.variable, show="•", placeholder_text=placeholder, height=34)
        self.entry.grid(row=row, column=1, sticky="ew", pady=style.GAP // 2 + 2)
        self.toggle = icon_button(parent, "eye", self._toggle, tr("Mostrar u ocultar"))
        self.toggle.grid(row=row, column=2, sticky="w", padx=(8, pad))
        self.label = field_label(parent, label)
        self.label.grid(row=row, column=0, sticky="w", padx=(pad, style.GAP), pady=style.GAP // 2 + 2)
        self._widgets = [self.label, self.entry, self.toggle]

    def get(self) -> str:
        return self.variable.get()

    def set(self, value: str) -> None:
        self.variable.set(value)

    def hide(self) -> None:
        for widget in self._widgets:
            hide(widget)

    def show(self) -> None:
        for widget in self._widgets:
            show(widget)

    def _toggle(self) -> None:
        self.entry.configure(show="" if self.entry.cget("show") else "•")


# * Arrastrar y soltar --------------------------------------------------------


def enable_file_drop(widget, callback: Callable[[list[Path]], None], recursive: bool = True) -> None:
    """
    Permite soltar archivos del explorador sobre ``widget`` (y sus hijos).
    ``callback`` recibe la lista de rutas soltadas.
    """

    def on_drop(event) -> str:
        files = [Path(item) for item in widget.tk.splitlist(event.data)]
        callback(files)
        return event.action

    targets: Iterable = [widget]
    if recursive:
        targets = _walk(widget)
    for target in targets:
        try:
            target.drop_target_register(DND_FILES)
            target.dnd_bind("<<Drop>>", on_drop)
        except (AttributeError, tk.TclError):
            continue


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


# * Tooltip -----------------------------------------------------------------


class ToolTip:
    """
    Tooltip que aparece tras una breve pausa sobre el widget.

    - Siempre dentro del monitor donde esta el widget (cerca del borde derecho
      se corre hacia la izquierda; si no cabe debajo, se muestra encima).
    - No es "siempre encima" y se cierra cuando la aplicacion pierde el foco:
      antes quedaba flotando sobre el otro programa al usar Alt+Tab.
    - No aparece si la aplicacion no esta activa.
    """

    DELAY_MS = 450
    MARGIN = 8  # distancia minima al borde del monitor
    _active: "ToolTip | None" = None  # a lo sumo uno visible
    _hooked: ClassVar[set[str]] = set()  # ventanas con el aviso de desactivacion instalado

    def __init__(self, widget, text: str | Callable[[], str], above: bool = False) -> None:
        self.widget = widget
        self.text = text  # texto fijo o funcion que lo calcula al mostrarse
        self.above = above  # mostrar encima del widget (p. ej. en la barra de estado)
        self.window: tk.Toplevel | None = None
        self._after_id: str | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._after_id = self.widget.after(self.DELAY_MS, self._show)

    def _cancel(self) -> None:
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self) -> None:
        self._after_id = None
        text = self.text() if callable(self.text) else self.text
        if self.window or not text or not self.widget.winfo_exists() or not _app_is_active(self.widget):
            return
        if ToolTip._active is not None:
            ToolTip._active.hide()
        self._hook_deactivation()
        self.window = tk.Toplevel(self.widget)
        self.window.withdraw()  # se ubica antes de verse: sin saltos
        self.window.wm_overrideredirect(True)
        tk.Label(
            self.window,
            text=text,
            justify="left",
            wraplength=420,
            background=style.themed(("gray20", "gray85")),
            foreground=style.themed(("white", "gray10")),
            font=(style.FONT_FAMILY, 9),
            padx=8,
            pady=4,
        ).pack()
        self.window.update_idletasks()
        x, y = self.position(self.window.winfo_reqwidth(), self.window.winfo_reqheight())
        self.window.wm_geometry(f"+{x}+{y}")
        self.window.deiconify()
        self.window.lift()
        ToolTip._active = self

    def position(self, width: int, height: int) -> tuple[int, int]:
        """Esquina superior izquierda del tooltip, dentro del monitor del widget."""
        widget = self.widget
        left, top, right, bottom = monitor_work_area(widget)
        x = widget.winfo_rootx() + 8
        below = widget.winfo_rooty() + widget.winfo_height() + 6
        above = widget.winfo_rooty() - height - 6
        y = above if self.above or below + height > bottom - self.MARGIN else below
        x = max(left + self.MARGIN, min(x, right - width - self.MARGIN))
        y = max(top + self.MARGIN, min(y, bottom - height - self.MARGIN))
        return x, y

    def _hook_deactivation(self) -> None:
        """Cierra el tooltip visible cuando la ventana pierde el foco (Alt+Tab, otra app)."""
        top = self.widget.winfo_toplevel()
        if str(top) in ToolTip._hooked:
            return
        ToolTip._hooked.add(str(top))
        top.bind("<FocusOut>", lambda _e: top.after(60, ToolTip._hide_if_inactive), add="+")
        top.bind("<Unmap>", lambda _e: ToolTip._hide_active(), add="+")

    @staticmethod
    def _hide_if_inactive() -> None:
        active = ToolTip._active
        if active is not None and (not active.widget.winfo_exists() or not _app_is_active(active.widget)):
            active.hide()

    @staticmethod
    def _hide_active() -> None:
        if ToolTip._active is not None:
            ToolTip._active.hide()

    def hide(self, _event=None) -> None:
        self._cancel()
        if self.window:
            self.window.destroy()
            self.window = None
        if ToolTip._active is self:
            ToolTip._active = None


def _app_is_active(widget) -> bool:
    """La aplicacion tiene el foco del sistema (Tk devuelve None si es otra la activa)."""
    try:
        return widget.focus_get() is not None
    except (KeyError, tk.TclError):  # foco en una ventana de otra libreria
        return True


def monitor_work_area(widget, whole: bool = False) -> tuple[int, int, int, int]:
    """Area util (sin barra de tareas) del monitor donde esta ``widget``; con ``whole``, el monitor entero."""
    if sys.platform.startswith("win"):
        try:
            return _windows_work_area(
                widget.winfo_rootx() + widget.winfo_width() // 2,
                widget.winfo_rooty() + widget.winfo_height() // 2,
                whole,
            )
        except (OSError, AttributeError):
            pass
    return 0, 0, widget.winfo_screenwidth(), widget.winfo_screenheight()


def _windows_work_area(x: int, y: int, whole: bool = False) -> tuple[int, int, int, int]:
    class _Rect(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class _MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", _Rect), ("rcWork", _Rect), ("dwFlags", ctypes.c_ulong)]

    user32 = ctypes.windll.user32
    user32.MonitorFromPoint.restype = ctypes.c_void_p
    monitor = user32.MonitorFromPoint(ctypes.wintypes.POINT(x, y), 2)  # MONITOR_DEFAULTTONEAREST
    info = _MonitorInfo()
    info.cbSize = ctypes.sizeof(_MonitorInfo)
    if not user32.GetMonitorInfoW(ctypes.c_void_p(monitor), ctypes.byref(info)):
        raise OSError("GetMonitorInfoW")
    work = info.rcMonitor if whole else info.rcWork
    return work.left, work.top, work.right, work.bottom
