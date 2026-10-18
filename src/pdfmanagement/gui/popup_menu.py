"""
Menu emergente con el mismo aspecto que las listas desplegables.

Reemplaza a ``tk.Menu`` (que se dibuja con el estilo de Windows, distinto del
resto de la aplicacion) en el menu "Ver" y en los menus contextuales. Admite
el subconjunto de ``tk.Menu`` que usa la aplicacion, asi el cambio es directo::

    menu = PopupMenu(widget)
    menu.add_command(label="Copiar", accelerator="Ctrl+C", command=copiar)
    menu.add_checkbutton(label="Modo nocturno", variable=nocturno, command=...)
    menu.add_separator()
    menu.add_cascade(label="Color", menu=submenu)
    menu.tk_popup(x, y)  # coordenadas de pantalla

Se cierra al elegir una opcion, con Escape, al hacer clic fuera, al mover la
ventana o al cambiar de aplicacion.
"""

from __future__ import annotations

import sys
import time
import tkinter as tk
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

import customtkinter as ctk

from . import style
from .dropdown import ROW_HEIGHT
from .icons import icon
from .widgets import monitor_work_area

MIN_WIDTH = 190
OPEN_GRACE_SECONDS = 0.15  # el clic que abre el menu tambien llega a la ventana: no debe cerrarlo
TRANSPARENT = "#000001"  # color que Windows vuelve transparente (esquinas redondeadas)


@dataclass
class MenuItem:
    kind: str  # "command", "check", "cascade" o "separator"
    label: str = ""
    command: Callable[[], object] | None = None
    accelerator: str = ""
    enabled: bool = True
    variable: tk.BooleanVar | None = None
    submenu: PopupMenu | None = None


class PopupMenu:
    """Menu emergente con el estilo de la aplicacion (ver el docstring del modulo)."""

    _active: ClassVar[PopupMenu | None] = None  # menu principal abierto (uno a la vez)
    _open: ClassVar[set[PopupMenu]] = set()  # todos los menus y submenus con ventana abierta
    _root: ClassVar[tk.Misc | None] = None  # ventana principal (para saber si la app tiene el foco)
    _hooked: ClassVar[set[str]] = set()

    def __init__(self, master, tearoff: int = 0) -> None:
        del tearoff  # compatibilidad con tk.Menu
        self.master = master
        self.items: list[MenuItem] = []
        self.window: ctk.CTkToplevel | None = None
        self.parent: PopupMenu | None = None
        self._child: PopupMenu | None = None
        self._opened_at = 0.0

    # * Contenido (misma firma que tk.Menu) ------------------------------------------

    def add_command(
        self, label: str, command: Callable[[], object] | None = None, accelerator: str = "", state: str = "normal"
    ) -> None:
        self.items.append(MenuItem("command", label, command, accelerator, state != "disabled"))

    def add_checkbutton(
        self, label: str, variable: tk.BooleanVar, command: Callable[[], object] | None = None, state: str = "normal"
    ) -> None:
        self.items.append(MenuItem("check", label, command, enabled=state != "disabled", variable=variable))

    def add_separator(self) -> None:
        self.items.append(MenuItem("separator"))

    def add_cascade(self, label: str, menu: PopupMenu, state: str = "normal") -> None:
        menu.parent = self
        self.items.append(MenuItem("cascade", label, enabled=state != "disabled", submenu=menu))

    def labels(self, kinds: tuple[str, ...] = ("command", "check", "cascade")) -> list[str]:
        return [item.label for item in self.items if item.kind in kinds]

    def invoke(self, label: str) -> None:
        """Ejecuta la opcion ``label`` como si se eligiera (pruebas y atajos)."""
        item = next(item for item in self.items if item.label == label and item.kind != "separator")
        self._choose(item)

    # * Mostrar y cerrar --------------------------------------------------------------

    def tk_popup(self, x: int, y: int) -> None:
        """Abre el menu con su esquina superior izquierda en ``(x, y)`` (pantalla), dentro del monitor."""
        if self.parent is None:
            PopupMenu.close_everything()
            PopupMenu._active = self
            self._hook_root()
        if self.window is not None and self.window.winfo_exists():
            self.window.destroy()  # nunca dos ventanas para el mismo menu
        window = self.window = self._build()
        PopupMenu._open.add(self)
        # El foco queda en el menu (o en un submenu): si otra aplicacion pasa al frente, la
        # ventana principal no se entera; cada menu vigila su propia perdida de foco.
        window.bind("<FocusOut>", lambda _e: window.after(80, PopupMenu._close_if_inactive), add="+")
        window.update_idletasks()
        width, height = window.winfo_reqwidth(), window.winfo_reqheight()
        left, top, right, bottom = monitor_work_area(self.master)
        if x + width > right - 4:
            x = (x - width - self._parent_width()) if self.parent is not None else right - width - 4
        if y + height > bottom - 4:
            y = max(top + 4, bottom - height - 4)
        window.geometry(f"+{max(left + 4, x)}+{y}")
        window.deiconify()
        window.lift()
        window.focus_force()
        self._opened_at = time.monotonic()

    def grab_release(self) -> None:  # compatibilidad con tk.Menu (no hay grab)
        return

    def close(self) -> None:
        """Cierra este menu, sus submenus y, si es un submenu, nada mas."""
        if self._child is not None:
            self._child.close()
            self._child = None
        if self.window is not None and self.window.winfo_exists():
            self.window.destroy()
        self.window = None
        PopupMenu._open.discard(self)
        if PopupMenu._active is self:
            PopupMenu._active = None

    def close_all(self) -> None:
        """Cierra este menu y todos los demas abiertos (submenus incluidos)."""
        PopupMenu.close_everything()

    @staticmethod
    def close_everything() -> None:
        """Cierra todas las ventanas de menu abiertas: ninguna puede quedar suelta encima de todo."""
        for menu in list(PopupMenu._open):
            menu.close()
        PopupMenu._open.clear()
        PopupMenu._active = None

    def just_opened(self) -> bool:
        return time.monotonic() - self._opened_at < OPEN_GRACE_SECONDS

    @property
    def is_open(self) -> bool:
        return self.window is not None and self.window.winfo_exists()

    # * Construccion ----------------------------------------------------------------

    def _build(self) -> ctk.CTkToplevel:
        window = ctk.CTkToplevel(self.master.winfo_toplevel(), fg_color=TRANSPARENT)
        window.withdraw()
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        if sys.platform.startswith("win"):
            window.attributes("-transparentcolor", TRANSPARENT)
        frame = ctk.CTkFrame(
            window,
            corner_radius=8,
            border_width=1,
            border_color=style.CARD_BORDER,
            fg_color=style.CARD_BG,
            bg_color=TRANSPARENT,
        )
        frame.pack(fill="both", expand=True)
        has_checks = any(item.kind == "check" for item in self.items)
        rows = ctk.CTkFrame(frame, fg_color="transparent")
        rows.pack(fill="both", expand=True, padx=6, pady=6)
        rows.grid_columnconfigure(0, weight=1, minsize=MIN_WIDTH)
        for index, item in enumerate(self.items):
            if item.kind == "separator":
                ctk.CTkFrame(rows, height=1, fg_color=style.CARD_BORDER).grid(
                    row=index, column=0, sticky="ew", padx=8, pady=4
                )
                continue
            self._add_row(rows, index, item, has_checks)
        window.bind("<Escape>", lambda _e: self.close_all())
        return window

    def _add_row(self, rows, index: int, item: MenuItem, has_checks: bool) -> None:
        checked = item.kind == "check" and item.variable is not None and item.variable.get()
        image = None
        if checked:
            image = icon("check", 14, style.TEXT)
        elif has_checks:
            image = icon("blank", 14, style.TEXT)  # misma sangria que las opciones marcadas
        button = ctk.CTkButton(
            rows,
            text=item.label,
            image=image,
            compound="left",
            anchor="w",
            height=ROW_HEIGHT,
            corner_radius=6,
            fg_color="transparent",
            hover_color=style.HOVER,
            text_color=style.TEXT if item.enabled else style.TEXT_DISABLED,
            font=style.fonts().body,
            state="normal" if item.enabled else "disabled",
            command=lambda: self._choose(item),
        )
        button.grid(row=index, column=0, sticky="ew", pady=1)
        hint = "›" if item.kind == "cascade" else item.accelerator
        if hint:
            label = ctk.CTkLabel(
                button, text=hint, font=style.fonts().small, text_color=style.TEXT_MUTED, fg_color="transparent"
            )
            label.place(relx=1.0, rely=0.5, x=-10, anchor="e")
            if item.enabled:
                label.bind("<Button-1>", lambda _e: self._choose(item))
            # Deja espacio a la derecha para el atajo (el texto del boton no lo pisa).
            button.configure(width=button.winfo_reqwidth() + label.winfo_reqwidth() + 24)
        if item.kind == "cascade" and item.enabled:
            button.bind("<Enter>", lambda _e: self._open_submenu(item, button), add="+")
        elif self._child is not None or item.kind != "cascade":
            button.bind("<Enter>", lambda _e: self._close_child(), add="+")

    def _choose(self, item: MenuItem) -> None:
        if not item.enabled:
            return
        if item.kind == "cascade":
            return  # se abre al pasar el cursor
        if item.kind == "check" and item.variable is not None:
            item.variable.set(not item.variable.get())
        self.close_all()
        if item.command is not None:
            item.command()

    def _open_submenu(self, item: MenuItem, button) -> None:
        submenu = item.submenu
        if submenu is None or (self._child is submenu and submenu.is_open):
            return
        self._close_child()
        self._child = submenu
        submenu.tk_popup(button.winfo_rootx() + button.winfo_width() + 6, button.winfo_rooty() - 6)

    def _close_child(self) -> None:
        if self._child is not None:
            self._child.close()
            self._child = None

    def _parent_width(self) -> int:
        parent = self.parent
        if parent is None or parent.window is None:
            return 0
        return parent.window.winfo_width() + 12

    # * Cierre al hacer clic fuera ------------------------------------------------------

    def _hook_root(self) -> None:
        root = self.master.winfo_toplevel()
        PopupMenu._root = root
        if str(root) in PopupMenu._hooked:
            return
        PopupMenu._hooked.add(str(root))
        for sequence in ("<Button-1>", "<Button-3>"):
            root.bind(sequence, lambda _e: PopupMenu._close_active(), add="+")
        # Estos eventos llegan tambien de cada widget de la ventana: solo cuentan los de la ventana.
        for sequence in ("<Configure>", "<Unmap>"):
            root.bind(sequence, lambda e: PopupMenu._close_active() if e.widget is root else None, add="+")
        root.bind("<FocusOut>", lambda _e: root.after(80, PopupMenu._close_if_inactive), add="+")

    @staticmethod
    def _close_active() -> None:
        active = PopupMenu._active
        if active is not None and active.just_opened():
            return
        PopupMenu.close_everything()

    @staticmethod
    def _close_if_inactive() -> None:
        """Otra aplicacion paso al frente (Alt+Tab): ningun menu debe quedar encima de ella."""
        if not PopupMenu._open:
            return
        root = PopupMenu._root
        try:
            focused = root.focus_get() if root is not None else None
        except (KeyError, tk.TclError):
            focused = None
        if focused is None:
            PopupMenu.close_everything()
