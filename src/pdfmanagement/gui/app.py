"""
Ventana principal: barra lateral de navegacion, area de paginas y barra de estado.
"""

import logging
import os
import sys
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image
from tkinterdnd2 import TkinterDnD

from .. import __app_name__, __version__, core, paths
from ..config import Settings
from . import style
from .dialogs import HelpWindow
from .icons import icon
from .pages import PAGES
from .pages.base import BasePage
from .system import open_path, reveal_in_folder
from .tasks import TaskRunner
from .widgets import ToolTip, hide, show

logger = logging.getLogger(__name__)


class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
    """Ventana CustomTkinter con soporte de arrastrar y soltar (tkdnd)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)  # noqa: SLF001 - API documentada de tkinterdnd2


class MainWindow:
    """Orquesta la ventana, las paginas y los servicios compartidos."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        ctk.set_appearance_mode(settings.appearance_mode)
        ctk.set_default_color_theme(str(paths.THEMES_DIR / f"{settings.color_theme}.json"))
        ctk.set_widget_scaling(settings.ui_scaling)

        self.root = DnDCTk(fg_color=style.CONTENT_BG)
        self.root.title(__app_name__)
        if paths.APP_ICON.exists():
            self.root.iconbitmap(str(paths.APP_ICON))
        self.root.geometry(self._initial_geometry())
        self.root.minsize(980, 640)
        if settings.window_maximized:
            self.root.after(0, lambda: self.root.state("zoomed"))
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.report_callback_exception = self._on_callback_exception
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self.runner = TaskRunner(self.root, self._on_busy_change)
        self.pages: dict[str, BasePage] = {}
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.current_page: str | None = None
        self._last_result: Path | None = None

        self._build_sidebar()
        self._build_content()
        self._build_status_bar()
        self._bind_shortcuts()

    # * Construccion ----------------------------------------------------------

    def _initial_geometry(self) -> str:
        width, height = self.settings.window_width, self.settings.window_height
        x = max((self.root.winfo_screenwidth() - width) // 2, 0)
        y = max((self.root.winfo_screenheight() - height) // 3, 0)
        return f"{width}x{height}+{x}+{y}"

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(self.root, width=style.SIDEBAR_WIDTH, corner_radius=0, fg_color=style.SIDEBAR_BG)
        sidebar.grid(row=0, column=0, rowspan=2, sticky="nsw")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(len(PAGES) + 2, weight=1)

        brand = ctk.CTkFrame(sidebar, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=18, pady=(22, 18))
        if paths.APP_ICON.exists():
            logo = Image.open(paths.APP_ICON).convert("RGBA")
            self._logo = ctk.CTkImage(logo, logo, size=(30, 30))
            ctk.CTkLabel(brand, text="", image=self._logo).pack(side="left", padx=(0, 10))
        titles = ctk.CTkFrame(brand, fg_color="transparent")
        titles.pack(side="left")
        ctk.CTkLabel(titles, text=__app_name__, font=style.fonts().brand, anchor="w").pack(anchor="w")
        ctk.CTkLabel(
            titles, text=f"Version {__version__}", font=style.fonts().small, text_color=style.TEXT_MUTED, anchor="w"
        ).pack(anchor="w")

        for index, page_class in enumerate(PAGES, start=1):
            button = ctk.CTkButton(
                sidebar,
                text=f"  {page_class.name}",
                anchor="w",
                height=40,
                corner_radius=8,
                font=style.fonts().body,
                command=lambda name=page_class.name: self.show_page(name),
            )
            button.grid(row=index, column=0, sticky="ew", padx=12, pady=2)
            ToolTip(button, f"{page_class.title}  (Ctrl+{index})")
            self.nav_buttons[page_class.name] = button

        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer.grid(row=len(PAGES) + 3, column=0, sticky="ew", padx=12, pady=16)
        footer.grid_columnconfigure(0, weight=1)
        footer_style = {
            "anchor": "w",
            "height": 36,
            "corner_radius": 8,
            "fg_color": "transparent",
            "hover_color": style.HOVER,
            "text_color": style.TEXT,
            "font": style.fonts().body,
        }
        self.theme_button = ctk.CTkButton(footer, text="", image=icon("moon", 18), command=self.toggle_appearance, **footer_style)
        self.theme_button.grid(row=0, column=0, sticky="ew")
        help_button = ctk.CTkButton(footer, text="  Ayuda", image=icon("help", 18), command=self.open_help, **footer_style)
        help_button.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        ToolTip(help_button, "Guia de uso (F1)")
        self._refresh_theme_button()
        self._refresh_nav()

    def _build_content(self) -> None:
        self.content = ctk.CTkFrame(self.root, fg_color="transparent", corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

    def _build_status_bar(self) -> None:
        bar = ctk.CTkFrame(self.root, height=40, corner_radius=0, fg_color=style.SIDEBAR_BG)
        bar.grid(row=1, column=1, sticky="ew")
        bar.grid_columnconfigure(2, weight=1)

        self.status_icon = ctk.CTkLabel(bar, text="", width=20)
        self.status_icon.grid(row=0, column=0, padx=(style.PAD, 6), pady=8)
        self.progress = ctk.CTkProgressBar(bar, width=90, height=6, mode="indeterminate")
        self.status_label = ctk.CTkLabel(bar, text="Listo", font=style.fonts().small, text_color=style.TEXT_MUTED, anchor="w")
        self.status_label.grid(row=0, column=2, sticky="ew")

        self.open_result_button = ctk.CTkButton(
            bar, text="Abrir", width=70, height=26, font=style.fonts().small,
            command=lambda: self._last_result and open_path(self._last_result),
        )
        self.reveal_result_button = ctk.CTkButton(
            bar, text="Mostrar en carpeta", width=130, height=26, font=style.fonts().small,
            fg_color="transparent", border_width=1, border_color=style.CARD_BORDER,
            text_color=style.TEXT, hover_color=style.HOVER,
            command=lambda: self._last_result and reveal_in_folder(self._last_result),
        )

    def _bind_shortcuts(self) -> None:
        for index, page_class in enumerate(PAGES, start=1):
            self.root.bind(f"<Control-Key-{index}>", lambda _event, name=page_class.name: self.show_page(name))
        self.root.bind("<F1>", lambda _event: self.open_help())

    # * Navegacion ------------------------------------------------------------

    def show_page(self, name: str) -> None:
        """Muestra la pagina ``name`` creandola la primera vez (carga diferida)."""
        if name not in self.pages:
            page_class = next(page for page in PAGES if page.name == name)
            self.pages[name] = page_class(self.content, self)
        if self.current_page and self.current_page != name:
            hide(self.pages[self.current_page])
        page = self.pages[name]
        page.grid(row=0, column=0, sticky="nsew")
        self.current_page = name
        self._refresh_nav()
        page.on_show()

    def _refresh_nav(self) -> None:
        accent = style.accent_color()
        for name, button in self.nav_buttons.items():
            page_class = next(page for page in PAGES if page.name == name)
            selected = name == self.current_page
            button.configure(
                fg_color=accent if selected else "transparent",
                hover_color=style.accent_hover_color() if selected else style.HOVER,
                text_color=style.WHITE if selected else style.TEXT,
                image=icon(page_class.icon_name, 18, style.WHITE if selected else style.TEXT),
            )

    # * Apariencia ------------------------------------------------------------

    def set_appearance_mode(self, mode: str) -> None:
        self.settings.appearance_mode = mode
        ctk.set_appearance_mode(mode)
        self.save_settings()
        self._refresh_theme_button()

    def toggle_appearance(self) -> None:
        self.set_appearance_mode("Light" if ctk.get_appearance_mode() == "Dark" else "Dark")

    def set_ui_scaling(self, scaling: float) -> None:
        self.settings.ui_scaling = scaling
        ctk.set_widget_scaling(scaling)
        self.save_settings()

    def _refresh_theme_button(self) -> None:
        dark = ctk.get_appearance_mode() == "Dark"
        self.theme_button.configure(
            text="  Modo claro" if dark else "  Modo oscuro", image=icon("sun" if dark else "moon", 18)
        )

    def save_settings(self) -> None:
        try:
            self.settings.save()
        except OSError as error:
            logger.error("No se pudieron guardar las preferencias: %s", error)

    # * Notificaciones --------------------------------------------------------

    def _on_busy_change(self, busy: bool, message: str) -> None:
        if busy:
            self._hide_result_actions()
            hide(self.status_icon)
            self.progress.grid(row=0, column=1, padx=(style.PAD, 10))
            self.progress.start()
            self.status_label.configure(text=f"{message}...", text_color=style.TEXT)
        else:
            self.progress.stop()
            hide(self.progress)
            show(self.status_icon)
            if self.status_label.cget("text").endswith("..."):
                self._set_status("Listo")

    def _set_status(self, text: str, icon_name: str | None = None, color=style.TEXT_MUTED) -> None:
        self.status_icon.configure(image=icon(icon_name, 16, color) if icon_name else None)
        self.status_label.configure(text=text, text_color=color if icon_name else style.TEXT_MUTED)

    def _hide_result_actions(self) -> None:
        hide(self.open_result_button)
        hide(self.reveal_result_button)

    def notify_success(self, title: str, result: Path) -> None:
        """Informa el resultado en la barra de estado sin interrumpir al usuario."""
        logger.debug("%s: %s", title, result)
        self._last_result = result
        self._set_status(f"{title}: {result.name}", "check", style.SUCCESS)
        if not self.runner.busy:
            self.reveal_result_button.grid(row=0, column=3, padx=(8, 6))
            self.open_result_button.grid(row=0, column=4, padx=(0, style.PAD))
        if self.settings.open_after_save:
            open_path(result)

    def show_error(self, error: BaseException) -> None:
        """Muestra un error. Los inesperados se registran con su traza completa."""
        if isinstance(error, core.PdfManagementError):
            logger.warning("%s", error)
            message = str(error)
        else:
            logger.error("Error inesperado", exc_info=(type(error), error, error.__traceback__))
            message = (
                f"Ocurrio un error inesperado:\n{error}\n\n"
                f"El detalle quedo registrado en {paths.LOG_DIR / 'error.log'}"
            )
        self._hide_result_actions()
        self._set_status("La operacion no se completo", "info", style.DANGER)
        messagebox.showerror("No se pudo completar la operacion", message, parent=self.root)

    def _on_callback_exception(self, exc_type, exc_value, exc_traceback) -> None:
        self.show_error(exc_value.with_traceback(exc_traceback))

    # * Ventanas y ciclo de vida ----------------------------------------------

    def open_help(self) -> None:
        if getattr(self, "_help", None) is not None and self._help.winfo_exists():
            self._help.focus()
            return
        self._help = HelpWindow(self.root)

    def run(self) -> None:
        initial = self.settings.initial_page
        self.show_page(initial if initial in self.nav_buttons else PAGES[0].name)
        self.root.mainloop()

    def restart(self) -> None:
        """Reinicia el proceso para aplicar cambios que requieren recargar el tema."""
        self.close(exit_process=False)
        os.execl(sys.executable, sys.executable, *sys.argv)

    def close(self, exit_process: bool = True) -> None:
        self._remember_geometry()
        for page in self.pages.values():
            page.on_close()
        self.runner.shutdown()
        self.root.destroy()
        if exit_process:
            sys.exit(0)

    def _remember_geometry(self) -> None:
        maximized = self.root.state() == "zoomed"
        self.settings.window_maximized = maximized
        if not maximized:
            # CTk guarda el tamano sin escalar en estos atributos.
            self.settings.window_width = int(getattr(self.root, "_current_width", self.root.winfo_width()))
            self.settings.window_height = int(getattr(self.root, "_current_height", self.root.winfo_height()))
        self.save_settings()
