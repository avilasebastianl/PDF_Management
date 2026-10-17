"""
Componentes reutilizables de la interfaz.
"""

import tkinter as tk
from collections.abc import Callable, Iterable
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from tkinterdnd2 import DND_FILES

from . import style
from .icons import icon

FileTypes = tuple[tuple[str, str], ...]
PDF_FILETYPES: FileTypes = (("Archivos PDF", "*.pdf"),)
LABEL_COLUMN_WIDTH = 170  # alinea los campos de todas las tarjetas


def format_size(size_bytes: int) -> str:
    """Tamano legible: ``532 B``, ``1.4 MB``."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def hide(widget) -> None:
    """
    Oculta un widget ubicado con ``grid`` recordando sus opciones.

    CustomTkinter repite la ultima llamada a ``grid`` al cambiar la escala, lo
    que volveria a mostrar widgets ocultos con ``grid_remove``; por eso se
    olvida esa llamada y se guarda aparte para ``show``.
    """
    call = getattr(widget, "_last_geometry_manager_call", None)
    if call:
        widget._hidden_grid_kwargs = call["kwargs"]
        widget._last_geometry_manager_call = None
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
        image=icon(icon_name, 16, style.WHITE) if icon_name else None,
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
        height=34,
        fg_color="transparent",
        hover_color=style.HOVER,
        border_width=1,
        border_color=style.CARD_BORDER,
        text_color=style.TEXT,
        font=style.fonts().body,
        corner_radius=8,
        **kwargs,
    )


def icon_button(parent, icon_name: str, command: Callable, tooltip: str, size: int = 32, **kwargs) -> ctk.CTkButton:
    """Boton cuadrado solo con icono y tooltip."""
    button = ctk.CTkButton(
        parent,
        text="" if icon(icon_name) else tooltip[:1],
        image=icon(icon_name, 16),
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
    return button


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
                self, text=description, font=style.fonts().small, text_color=style.TEXT_MUTED, anchor="w", justify="left"
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
        self.button = secondary_button(parent, "Examinar", self.browse, "folder", width=110)

        if stacked:
            label_widget.grid(row=row, column=0, columnspan=3, sticky="w", padx=pad, pady=(style.GAP, 2))
            self.entry.grid(row=row + 1, column=0, columnspan=2, sticky="ew", padx=(pad, 6))
            self.button.grid(row=row + 1, column=2, sticky="e", padx=(0, pad))
        else:
            label_widget.grid(row=row, column=0, sticky="w", padx=(pad, style.GAP), pady=style.GAP // 2 + 2)
            self.entry.grid(row=row, column=1, sticky="ew", pady=style.GAP // 2 + 2)
            self.button.grid(row=row, column=2, sticky="e", padx=(8, pad), pady=style.GAP // 2 + 2)

        if mode == "open":
            enable_file_drop(self.entry, self._on_drop)

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
        options = {"filetypes": self.filetypes, "initialdir": str(initial) if initial else None}
        if self.mode == "save":
            chosen = filedialog.asksaveasfilename(
                title="Guardar como",
                defaultextension=".pdf",
                initialfile=current.name if current else "",
                **options,
            )
            if chosen:
                self.set(Path(chosen))
                self.confirmed_path = Path(chosen)
        else:
            chosen = filedialog.askopenfilename(title="Seleccionar archivo", **options)
            if chosen:
                self.set(Path(chosen))

    def _on_drop(self, files: list[Path]) -> None:
        if files:
            self.set(files[0])

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
        self.toggle = icon_button(parent, "eye", self._toggle, "Mostrar u ocultar")
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
    """Tooltip sencillo que aparece tras una breve pausa sobre el widget."""

    DELAY_MS = 450

    def __init__(self, widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.window: tk.Toplevel | None = None
        self._after_id: str | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._after_id = self.widget.after(self.DELAY_MS, self._show)

    def _cancel(self) -> None:
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self) -> None:
        if self.window or not self.text:
            return
        x = self.widget.winfo_rootx() + 8
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self.window,
            text=self.text,
            background=style.themed(("gray20", "gray85")),
            foreground=style.themed(("white", "gray10")),
            font=(style.FONT_FAMILY, 9),
            padx=8,
            pady=4,
        ).pack()

    def _hide(self, _event=None) -> None:
        self._cancel()
        if self.window:
            self.window.destroy()
            self.window = None
