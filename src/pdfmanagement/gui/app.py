"""
Ventana principal: barra lateral de navegacion, area de paginas y barra de estado.
"""

import logging
import os
import platform
import sys
import time
import tkinter as tk
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk
from PIL import ImageGrab, ImageTk
from tkinterdnd2 import TkinterDnD

from .. import __app_name__, __version__, core, logging_setup, paths
from ..config import UI_SCALING_OPTIONS, Settings
from ..i18n import tr
from . import icons, style
from .appearance import AppearanceScheduler, frozen_redraw
from .dialogs import HelpWindow
from .events import debug_event, log_event
from .icons import icon
from .pages import PAGES
from .pages.base import BasePage
from .pages.registry import page_label
from .popup_menu import PopupMenu
from .status_bar import StatusBar
from .system import open_path
from .tasks import TaskRunner
from .widgets import ToolTip, hide, monitor_work_area, show

logger = logging.getLogger(__name__)

PREBUILD_DELAY_MS = 600  # espera tras el arranque antes de precargar paginas
PREBUILD_INTERVAL_MS = 150  # pausa entre paginas precargadas o reapiladas
RESTACK_DELAY_MS = 400  # espera tras redimensionar antes de reapilar paginas
SIDEBAR_ANIMATION_MS = 260  # duracion de contraer/expandir el menu lateral
SIDEBAR_FRAME_MS = 6  # pausa entre cuadros (cada cuadro se pinta enseguida)
RESIZE_LOG_DELAY_MS = 600  # se registra el tamano final, no cada paso del arrastre
# Fundidos de la ventana (modos de lectura, tamano de la interfaz y cierre).
FADE_IN_MS = 240  # la cortina con la imagen anterior se desvanece en este tiempo
CLOSE_FADE_MS = 140
FADE_FRAME_MS = 8

# Nombres legibles de las preferencias para el registro de cambios.
SETTING_LABELS = {
    "window_width": "Ancho de ventana",
    "window_height": "Alto de ventana",
    "window_maximized": "Ventana maximizada",
    "appearance_mode": "Modo",
    "color_theme": "Color de acento",
    "ui_scaling": "Tamano de la interfaz",
    "initial_page": "Pagina inicial",
    "open_after_save": "Abrir el archivo al terminar",
    "output_dir": "Carpeta de salida",
    "debug_logging": "Registro detallado",
    "sidebar_collapsed": "Menu lateral contraido",
    "language": "Idioma",
    "viewer_night_mode": "Visor en modo nocturno",
    "viewer_two_pages": "Visor a dos paginas",
}


class DnDCTk(ctk.CTk, TkinterDnD.DnDWrapper):
    """Ventana CustomTkinter con soporte de arrastrar y soltar (tkdnd)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)  # noqa: SLF001 - API documentada de tkinterdnd2


class MainWindow:
    """Orquesta la ventana, las paginas y los servicios compartidos."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._started = time.monotonic()
        self._closing = False
        self.animations = True  # las pruebas las desactivan (fundidos instantaneos)
        self._in_transition = False
        self.ui_scaling = settings.ui_scaling  # tamano actual; puede diferir del guardado (cambio temporal)
        self._settings_snapshot = asdict(settings)
        if settings.debug_logging:
            logging_setup.set_debug(True)
        # Iconos y fuentes quedan ligados a la ventana que los creo: se
        # descartan para poder crear otra ventana en el mismo proceso.
        icons.icon.cache_clear()
        style.fonts.cache_clear()
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
        self.root.protocol("WM_DELETE_WINDOW", self.request_close)
        self.root.report_callback_exception = self._on_callback_exception
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self.runner = TaskRunner(self.root, self._on_busy_change)
        self.appearance = AppearanceScheduler(
            self.root, lambda: [page for name, page in self.pages.items() if name != self.current_page]
        )
        self.pages: dict[str, BasePage] = {}
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self._nav_state: dict[str, bool] = {}
        self.current_page: str | None = None
        self._deferred_success: tuple[str, Path] | None = None
        self._last_size: tuple[int, int] | None = None
        self._restack_job: str | None = None
        self._resize_log_job: str | None = None
        self._sidebar_animation: tuple[float, int, int, float] | None = None
        self._help: HelpWindow | None = None
        self.settings_listeners: list = []  # se llaman tras guardar con las claves que cambiaron

        self._build_sidebar()
        self._build_content()
        self._build_status_bar()
        self._bind_shortcuts()
        self.root.bind("<Configure>", self._on_root_configure, add="+")
        self._log_session_start()

    def _log_session_start(self) -> None:
        settings = self.settings
        log_event(
            "Sesion",
            "Inicio de %s %s",
            __app_name__,
            __version__,
            python=platform.python_version(),
            sistema=platform.platform(terse=True),
            pantalla=f"{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}",
            escala_ui=f"{round(settings.ui_scaling * 100)}%",
            tema=f"{settings.appearance_mode}/{settings.color_theme}",
            modo_detallado=logging_setup.is_debug(),
            datos=paths.DATA_DIR,
        )

    # * Construccion ----------------------------------------------------------

    def _initial_geometry(self) -> str:
        # Nunca mas grande que la pantalla (deja sitio para la barra de tareas).
        width = min(self.settings.window_width, self.root.winfo_screenwidth() - 40)
        height = min(self.settings.window_height, self.root.winfo_screenheight() - 80)
        x = max((self.root.winfo_screenwidth() - width) // 2, 0)
        y = max((self.root.winfo_screenheight() - height) // 3, 0)
        return f"{width}x{height}+{x}+{y}"

    def _build_sidebar(self) -> None:
        collapsed = self.settings.sidebar_collapsed
        width = style.SIDEBAR_COLLAPSED_WIDTH if collapsed else style.SIDEBAR_WIDTH
        self.sidebar = sidebar = ctk.CTkFrame(self.root, width=width, corner_radius=0, fg_color=style.SIDEBAR_BG)
        sidebar.grid(row=0, column=0, rowspan=2, sticky="nsw")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(len(PAGES) + 2, weight=1)

        # Cabecera: boton para contraer/expandir el menu y nombre de la aplicacion.
        header = ctk.CTkFrame(sidebar, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(18, 14))
        self.sidebar_toggle = ctk.CTkButton(
            header,
            text="",
            image=icon("menu", 18),
            width=40,
            height=40,
            corner_radius=8,
            fg_color="transparent",
            hover_color=style.HOVER,
            command=self.toggle_sidebar,
        )
        self.sidebar_toggle.pack(side="left")
        ToolTip(
            self.sidebar_toggle,
            lambda: tr("Expandir el menú") if self.settings.sidebar_collapsed else tr("Contraer el menú"),
        )
        self._brand = ctk.CTkFrame(header, fg_color="transparent")
        ctk.CTkLabel(self._brand, text=__app_name__, font=style.fonts().brand, anchor="w").pack(anchor="w")
        ctk.CTkLabel(
            self._brand,
            text=tr("Versión {version}", version=__version__),
            font=style.fonts().small,
            text_color=style.TEXT_MUTED,
            anchor="w",
        ).pack(anchor="w")

        for index, page_class in enumerate(PAGES, start=1):
            button = ctk.CTkButton(
                sidebar,
                text=f"  {page_label(page_class.name)}",
                anchor="w",
                height=40,
                corner_radius=8,
                font=style.fonts().body,
                command=lambda name=page_class.name: self.show_page(name),
            )
            button.grid(row=index, column=0, sticky="ew", padx=12, pady=2)
            # Contraido solo se ven los iconos: el tooltip dice el nombre de la seccion.
            ToolTip(
                button,
                lambda page=page_class, key=index: (  # type: ignore[misc]
                    f"{page_label(page.name)}  (Ctrl+{key})"
                    if self.settings.sidebar_collapsed
                    else f"{page.title}  (Ctrl+{key})"
                ),
            )
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
        self.theme_button = ctk.CTkButton(
            footer, text="", image=icon("moon", 18), command=self.toggle_appearance, **footer_style
        )
        self.theme_button.grid(row=0, column=0, sticky="ew")
        ToolTip(self.theme_button, lambda: self._theme_label() if self.settings.sidebar_collapsed else "")
        self.scaling_button = ctk.CTkButton(
            footer, text="", image=icon("zoom_in", 18), command=self.show_scaling_menu, **footer_style
        )
        self.scaling_button.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        ToolTip(
            self.scaling_button,
            lambda: tr(
                "Tamaño de la interfaz solo por ahora: al reiniciar vuelve el de Ajustes ({predeterminado} %)",
                predeterminado=round(self.settings.ui_scaling * 100),
            ),
        )
        self.help_button = ctk.CTkButton(
            footer, text=f"  {tr('Ayuda')}", image=icon("help", 18), command=self.open_help, **footer_style
        )
        self.help_button.grid(row=2, column=0, sticky="ew", pady=(2, 0))
        ToolTip(self.help_button, tr("Guía de uso (F1)"))
        self._apply_sidebar_mode()
        self._refresh_nav()

    def set_chrome_visible(self, visible: bool) -> None:
        """Muestra u oculta el menu lateral y la barra de estado (pantalla completa del visor)."""
        for widget in (self.sidebar, self.status_bar):
            (show if visible else hide)(widget)
        self._place_main(None if visible else 0)

    def _place_main(self, left: int | None = None) -> None:
        """
        El contenido ocupa todo a la derecha del menu: ``x`` = ancho del menu y
        ``relwidth=1`` con ``width=-x``, asi sigue a la ventana al redimensionarla.
        Se coloca con ``place`` (no con ``grid``) para que la animacion del menu
        solo mueva ``x`` y al terminar no haya que cambiar de gestor de geometria
        (eso obligaba a remaquetar toda la seccion: ~110 ms pintandose a la vista).
        """
        if left is None:
            width = style.SIDEBAR_COLLAPSED_WIDTH if self.settings.sidebar_collapsed else style.SIDEBAR_WIDTH
            left = round(width * ctk.ScalingTracker.get_widget_scaling(self.sidebar))
        # place de Tk: el de CustomTkinter no admite width (lo exige en el constructor)
        tk.Frame.place_configure(self.main, x=left, y=0, relwidth=1, width=-left, relheight=1)

    def toggle_sidebar(self, animate: bool = True) -> None:
        """Contrae el menu lateral a solo iconos (o lo expande); se recuerda entre sesiones."""
        if self._sidebar_animation is not None:
            return  # se ignora el doble clic mientras se mueve
        self.settings.sidebar_collapsed = not self.settings.sidebar_collapsed
        self.save_settings()
        if animate and self.root.winfo_viewable():
            self._animate_sidebar()
        else:
            self._apply_sidebar_mode()

    def _animate_sidebar(self) -> None:
        """
        Desliza el menu y el contenido sin tirones.

        Redimensionar una seccion cuesta 150-220 ms (Tk vuelve a maquetar y
        pintar todo), demasiado para cada cuadro. Por eso el contenido se
        redimensiona una sola vez al principio, con el pintado congelado, y
        durante la animacion solo se desplaza (mover una ventana es barato)
        sobre el menu, que queda con su ancho maximo debajo, como un cajon.
        El dibujo de paginas del visor se pausa mientras tanto.

        Para que no parpadee: el contenido pasa de ``grid`` a ``place`` (y al
        final de vuelta) sin desmontarse nunca, y solo se congela el pintado
        una vez, al principio; lo que cambia al final queda tapado.
        """
        collapsed = self.settings.sidebar_collapsed
        start = self.sidebar.winfo_width()
        end = style.SIDEBAR_COLLAPSED_WIDTH if collapsed else style.SIDEBAR_WIDTH
        final_width = self.root.winfo_width() - round(end * ctk.ScalingTracker.get_widget_scaling(self.sidebar))
        self._unstack_hidden_pages()
        page = self.pages.get(self.current_page or "")
        old_width = self.main.winfo_width()
        with frozen_redraw(self.root):
            if not collapsed:  # el menu completo queda debajo y el contenido lo va descubriendo
                self.sidebar.configure(width=style.SIDEBAR_WIDTH)
                self._apply_sidebar_labels(collapsed=False)
            # Durante la animacion el ancho es fijo (el final) y solo cambia x.
            tk.Frame.place_configure(self.main, x=start, relwidth=0, width=final_width)
            self.main.lift(self.sidebar)
            self.root.update_idletasks()
            shift = 0.0
            if page is not None:
                shift = page.begin_slide((old_width - final_width) / 2)
                page.pause_rendering(True)
        self._sidebar_animation = (time.perf_counter(), start, end, shift)
        self._sidebar_step()

    def _sidebar_step(self) -> None:
        if self._sidebar_animation is None:
            return
        started, start, end, shift = self._sidebar_animation
        progress = min(1.0, (time.perf_counter() - started) * 1000 / SIDEBAR_ANIMATION_MS)
        eased = 1 - (1 - progress) ** 3  # arranca rapido y frena suave
        scaling = ctk.ScalingTracker.get_widget_scaling(self.sidebar)
        width = start / scaling + (end - start / scaling) * eased
        tk.Frame.place_configure(self.main, x=round(width * scaling))
        page = self.pages.get(self.current_page or "")
        if shift and page is not None:
            page.slide_content(shift * (1 - eased))  # las paginas centradas acompanan el movimiento
        self.root.update_idletasks()  # cada cuadro se pinta ya, a ritmo parejo
        if progress < 1.0:
            self.root.after(SIDEBAR_FRAME_MS, self._sidebar_step)
            return
        self._sidebar_animation = None
        # Lo que cambia ahora queda debajo del contenido: no hace falta congelar
        # el pintado (y repintar toda la ventana, que se notaba como un destello).
        self._apply_sidebar_mode()
        self._place_main()  # mismo tamano y posicion: no se remaqueta nada
        if page is not None:
            page.slide_content(0)
            page.pause_rendering(False)
        self._restack_job = self.root.after(RESTACK_DELAY_MS, self._restack_pages)

    def _unstack_hidden_pages(self) -> None:
        """Las secciones ocultas montadas encarecen cada cambio de tamano: se desmontan."""
        for name, page in self.pages.items():
            if name != self.current_page and page.winfo_manager() == "grid":
                hide(page)
        if self._restack_job:
            self.root.after_cancel(self._restack_job)
            self._restack_job = None

    def _apply_sidebar_mode(self) -> None:
        collapsed = self.settings.sidebar_collapsed
        self.sidebar.configure(width=style.SIDEBAR_COLLAPSED_WIDTH if collapsed else style.SIDEBAR_WIDTH)
        self._apply_sidebar_labels(collapsed)

    def _apply_sidebar_labels(self, collapsed: bool) -> None:
        if collapsed:
            self._brand.pack_forget()
        elif not self._brand.winfo_manager():
            self._brand.pack(side="left", padx=(8, 0))
        for page_class in PAGES:
            self.nav_buttons[page_class.name].configure(text="" if collapsed else f"  {page_label(page_class.name)}")
        self.help_button.configure(text="" if collapsed else f"  {tr('Ayuda')}")
        self._refresh_theme_button()
        self._refresh_scaling_button()

    def _build_content(self) -> None:
        # Contenido y barra de estado van juntos: al contraer el menu se desplazan como un bloque.
        self.main = ctk.CTkFrame(self.root, fg_color="transparent", corner_radius=0)
        self._place_main()
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(0, weight=1)
        self.content = ctk.CTkFrame(self.main, fg_color="transparent", corner_radius=0)
        self.content.grid(row=0, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

    def _build_status_bar(self) -> None:
        self.status_bar = StatusBar(self.main, on_view=lambda path: self.open_in("Visor", path))
        self.status_bar.grid(row=1, column=0, sticky="ew")

    def _bind_shortcuts(self) -> None:
        for index, page_class in enumerate(PAGES, start=1):
            self.root.bind(
                f"<Control-Key-{index}>",
                lambda _event, name=page_class.name, key=index: self.show_page(name, source=f"atajo Ctrl+{key}"),
            )
        self.root.bind("<F1>", lambda _event: self.open_help(source="atajo F1"))

    # * Navegacion ------------------------------------------------------------

    # Estrategia de paginas (medida en Windows):
    # - Las paginas construidas se apilan en la misma celda y mostrar una es
    #   solo traerla al frente (~40 ms frente a ~150 ms de mapearla con grid).
    # - Mantener paginas ocultas montadas encarece cada redimensionado (x4),
    #   asi que al redimensionar se desmontan y se reapilan de a una cuando
    #   la ventana queda quieta.

    def _ensure_page(self, name: str, reason: str = "al abrir") -> BasePage:
        """Construye la pagina ``name`` si aun no existe."""
        if name not in self.pages:
            page_class = next(page for page in PAGES if page.name == name)
            started = time.perf_counter()
            self.pages[name] = page_class(self.content, self)
            self._stack(self.pages[name], front=False)
            debug_event(
                "Interfaz", "Pagina %s construida %s (%.0f ms)", name, reason, (time.perf_counter() - started) * 1000
            )
        return self.pages[name]

    def _stack(self, page: BasePage, front: bool) -> None:
        if page.winfo_manager() != "grid":
            page.grid(row=0, column=0, sticky="nsew")
        if front:
            page.tkraise()
        else:
            page.lower()

    def show_page(self, name: str, source: str = "barra lateral") -> None:
        """Muestra la pagina ``name`` (la construye si la precarga aun no lo hizo)."""
        if name != self.current_page:
            log_event("Navegacion", "%s -> %s", self.current_page or "(inicio)", name, origen=source)
        previous = self.pages.get(self.current_page or "")
        if previous is not None and self.current_page != name:
            previous.on_hide()
        page = self._ensure_page(name)
        self.appearance.flush_page(page)  # por si quedo pendiente de un cambio de tema
        self._stack(page, front=True)
        self.current_page = name
        self._refresh_nav()
        page.on_show()

    def open_in(self, name: str, path: Path) -> None:
        """Muestra la seccion ``name`` y le entrega el archivo ``path``."""
        self.show_page(name, source=f"enviado ({path.name})")
        self.pages[name].receive_file(path)

    def _prebuild_pages(self) -> None:
        """
        Construye las paginas que faltan, una por ciclo libre, para que el
        primer cambio de seccion sea inmediato.
        """
        pending = [page.name for page in PAGES if page.name not in self.pages]
        if not pending:
            return
        delay = PREBUILD_INTERVAL_MS * 4 if self.runner.busy else PREBUILD_INTERVAL_MS
        if not self.runner.busy:
            self._ensure_page(pending[0], reason="en precarga")
        self.root.after(delay, self._prebuild_pages)

    def _on_root_configure(self, event) -> None:
        if event.widget is not self.root:
            return
        size = (event.width, event.height)
        if size == self._last_size:
            return  # solo se movio la ventana
        self._last_size = size
        for name, page in self.pages.items():
            if name != self.current_page and page.winfo_manager() == "grid":
                hide(page)
        if self._restack_job:
            self.root.after_cancel(self._restack_job)
        self._restack_job = self.root.after(RESTACK_DELAY_MS, self._restack_pages)
        if self._resize_log_job:
            self.root.after_cancel(self._resize_log_job)
        self._resize_log_job = self.root.after(RESIZE_LOG_DELAY_MS, self._log_window_size)

    def _log_window_size(self) -> None:
        self._resize_log_job = None
        if self.root.winfo_exists():
            debug_event(
                "Ventana",
                "Tamano %sx%s",
                self.root.winfo_width(),
                self.root.winfo_height(),
                estado="maximizada" if self.root.state() == "zoomed" else "normal",
            )

    def _restack_pages(self) -> None:
        """Vuelve a apilar, de a una, las paginas desmontadas al redimensionar."""
        self._restack_job = None
        unmounted = [
            page for name, page in self.pages.items() if name != self.current_page and page.winfo_manager() != "grid"
        ]
        if unmounted:
            self._stack(unmounted[0], front=False)
            if len(unmounted) > 1:
                self._restack_job = self.root.after(PREBUILD_INTERVAL_MS, self._restack_pages)

    def _refresh_nav(self) -> None:
        """Resalta la pagina actual; solo redibuja los botones que cambian."""
        accent = style.accent_color()
        for name, button in self.nav_buttons.items():
            page_class = next(page for page in PAGES if page.name == name)
            selected = name == self.current_page
            if self._nav_state.get(name) == selected:
                continue
            self._nav_state[name] = selected
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
        """Tamano de la interfaz elegido en Ajustes: se aplica y queda como predeterminado."""
        self.settings.ui_scaling = scaling
        self.save_settings()
        self.transition(lambda: self._apply_scaling(scaling))

    def preview_ui_scaling(self, scaling: float) -> None:
        """Tamano de la interfaz solo para esta sesion (boton del menu lateral); no se guarda."""
        if scaling == self.ui_scaling:
            return
        log_event("Apariencia", "Tamano temporal de la interfaz: %d%%", round(scaling * 100), guardado=False)
        self.transition(lambda: self._apply_scaling(scaling))

    def _apply_scaling(self, scaling: float) -> None:
        self.ui_scaling = scaling
        _prune_scaling_callbacks()
        ctk.set_widget_scaling(scaling)
        self._place_main()
        self._refresh_scaling_button()

    def show_scaling_menu(self) -> None:
        menu = PopupMenu(self.root)
        for option in UI_SCALING_OPTIONS:
            menu.add_checkbutton(
                label=f"{round(option * 100)} %",
                variable=tk.BooleanVar(value=option == self.ui_scaling),
                command=lambda value=option: self.preview_ui_scaling(value),  # type: ignore[misc]
            )
        if self.ui_scaling != self.settings.ui_scaling:
            menu.add_separator()
            menu.add_command(
                label=tr("Volver al predeterminado ({valor} %)", valor=round(self.settings.ui_scaling * 100)),
                command=lambda: self.preview_ui_scaling(self.settings.ui_scaling),
            )
        button = self.scaling_button
        menu.tk_popup(button.winfo_rootx() + button.winfo_width() + 6, button.winfo_rooty())

    def _refresh_scaling_button(self) -> None:
        percent = round(self.ui_scaling * 100)
        text = "" if self.settings.sidebar_collapsed else "  " + tr("Tamaño: {valor} %", valor=percent)
        if self.scaling_button.cget("text") != text:
            self.scaling_button.configure(text=text)

    # * Fundidos ----------------------------------------------------------------

    def fade(self, start: float, end: float, duration_ms: int) -> None:
        """Opacidad de la ventana principal de ``start`` a ``end`` (cierre)."""
        if not self.animations or not self.root.winfo_viewable():
            self.root.attributes("-alpha", end)
            return
        self._fade_window(self.root, start, end, duration_ms)

    @staticmethod
    def _fade_window(window, start: float, end: float, duration_ms: int) -> None:
        """
        La opacidad la aplica Windows sobre la imagen ya pintada: cada cuadro
        cuesta casi nada y el fundido sale parejo aunque haya mucho contenido.
        """
        started = time.perf_counter()
        while True:
            progress = min(1.0, (time.perf_counter() - started) * 1000 / duration_ms)
            eased = progress * progress * (3 - 2 * progress)  # suave al empezar y al terminar
            window.attributes("-alpha", start + (end - start) * eased)
            window.update_idletasks()
            if progress >= 1.0:
                return
            time.sleep(FADE_FRAME_MS / 1000)

    def transition(self, change) -> None:
        """
        Cambio grande de la ventana (modos de lectura, tamano de la interfaz) con
        un fundido cruzado, sin ver los pasos intermedios ni la ventana vacia.

        Reacomodar toda la ventana le cuesta a Tk 0,3-0,6 s y se pinta por
        partes. Por eso se cubre el monitor con una captura de como se ve ahora
        (una "cortina"), se aplica ``change`` debajo, se espera a que todo quede
        maquetado y dibujado (paginas del visor incluidas) y la cortina se
        desvanece mostrando el resultado.
        """
        if self._in_transition or not self.animations or not self.root.winfo_viewable():
            change()  # p. ej. F11 pulsada otra vez durante el fundido
            return
        self._in_transition = True
        curtain = self._show_curtain()
        try:
            change()
            self.root.update()  # el cambio de tamano de la ventana llega como eventos
            page = self.pages.get(self.current_page or "")
            if page is not None:
                page.flush_layout()
            self.root.update_idletasks()
        finally:
            if curtain is not None:
                self._fade_window(curtain, 1.0, 0.0, FADE_IN_MS)
                curtain.destroy()
            self._in_transition = False

    def _show_curtain(self) -> tk.Toplevel | None:
        """Ventana sin bordes, encima de todo, con la captura del monitor tal como se ve."""
        left, top, right, bottom = monitor_work_area(self.root, whole=True)
        try:
            image = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
        except OSError:  # captura no disponible (sesion remota bloqueada, etc.)
            return None
        curtain = tk.Toplevel(self.root)
        curtain.withdraw()
        curtain.overrideredirect(True)
        curtain.attributes("-topmost", True)
        curtain.geometry(f"{right - left}x{bottom - top}+{left}+{top}")
        photo = ImageTk.PhotoImage(image, master=curtain)
        label = tk.Label(curtain, image=photo, borderwidth=0, highlightthickness=0)
        label.image = photo  # type: ignore[attr-defined]  # Tk borra la imagen si nadie la referencia
        label.pack()
        curtain.deiconify()
        curtain.update()
        return curtain

    def _theme_label(self) -> str:
        return tr("Modo claro") if ctk.get_appearance_mode() == "Dark" else tr("Modo oscuro")

    def _refresh_theme_button(self) -> None:
        dark = ctk.get_appearance_mode() == "Dark"
        self.theme_button.configure(
            text="" if self.settings.sidebar_collapsed else f"  {self._theme_label()}",
            image=icon("sun" if dark else "moon", 18),
        )

    def set_debug_logging(self, enabled: bool) -> None:
        """Activa o desactiva el registro detallado sin reiniciar."""
        self.settings.debug_logging = enabled
        logging_setup.set_debug(enabled)
        self.save_settings()

    def save_settings(self) -> None:
        changed = self._log_settings_changes()
        try:
            self.settings.save()
        except OSError as error:
            logger.error("No se pudieron guardar las preferencias: %s", error)
            return
        for listener in self.settings_listeners:
            listener(changed)

    def _log_settings_changes(self) -> list[str]:
        """Registra cada preferencia que cambio desde el ultimo guardado (antes -> despues)."""
        current = asdict(self.settings)
        changed = []
        for key, value in current.items():
            previous = self._settings_snapshot.get(key)
            if previous != value:
                changed.append(key)
                log_event("Ajustes", "%s: %s -> %s", SETTING_LABELS.get(key, key), _show(previous), _show(value))
        self._settings_snapshot = current
        return changed

    # * Notificaciones --------------------------------------------------------

    def _on_busy_change(self, busy: bool, message: str) -> None:
        if busy:
            self.status_bar.set_busy(message, self.runner.pending)
        elif self._deferred_success is not None:
            self.status_bar.set_success(*self._deferred_success)
            self._deferred_success = None
        elif self.status_bar.state == "busy":
            self.status_bar.set_idle()

    def notify_success(self, title: str, result: Path) -> None:
        """Informa el resultado en la barra de estado sin interrumpir al usuario."""
        debug_event(self.current_page or "General", "Resultado notificado: %s", title, archivo=result)
        if self.runner.busy:
            # Quedan tareas en cola: el resultado se muestra cuando terminen todas.
            self._deferred_success = (title, result)
        else:
            self.status_bar.set_success(title, result)
        if self.settings.open_after_save:
            open_path(result)

    def show_error(self, error: BaseException) -> None:
        """Muestra un error. Los inesperados se registran con su traza completa."""
        if isinstance(error, core.PdfManagementError):
            log_event(
                self.current_page or "General",
                "Aviso mostrado al usuario: %s",
                error,
                level=logging.WARNING,
                tipo=type(error).__name__,
            )
            message = str(error)
        else:
            logger.error("Error inesperado", exc_info=(type(error), error, error.__traceback__))
            message = tr(
                "Ocurrió un error inesperado:\n{error}\n\nEl detalle quedó registrado en {log}",
                error=error,
                log=paths.LOG_DIR / "error.log",
            )
        self.status_bar.set_error(str(error))
        messagebox.showerror(tr("No se pudo completar la operación"), message, parent=self.root)

    def _on_callback_exception(self, exc_type, exc_value, exc_traceback) -> None:
        if self._closing:  # la ventana se esta destruyendo: un dialogo modal la bloquearia
            logger.error("Error durante el cierre", exc_info=(exc_type, exc_value, exc_traceback))
            return
        self.show_error(exc_value.with_traceback(exc_traceback))

    # * Ventanas y ciclo de vida ----------------------------------------------

    def open_help(self, section: str | None = None, source: str = "boton Ayuda") -> None:
        """Abre la guia de uso (o la trae al frente), opcionalmente en ``section``."""
        log_event("Ayuda", "Guia abierta", seccion=section or "inicio", origen=source)
        if self._help is not None and self._help.winfo_exists():
            if section:
                self._help.show_section(section)
            self._help.focus()
            return
        self._help = HelpWindow(self.root, section=section)

    def run(self) -> None:
        initial = self.settings.initial_page
        self.show_page(initial if initial in self.nav_buttons else PAGES[0].name)
        self.root.after(PREBUILD_DELAY_MS, self._prebuild_pages)
        self.root.mainloop()

    def restart(self) -> None:
        """Reinicia el proceso para aplicar cambios que requieren recargar el tema."""
        log_event("Sesion", "Reinicio solicitado para aplicar cambios")
        self.close(exit_process=False)
        os.execl(sys.executable, sys.executable, *sys.argv)

    def request_close(self) -> None:
        """Boton cerrar de la ventana: cada seccion puede impedirlo (cambios sin guardar)."""
        for name, page in self.pages.items():
            if not page.can_close():
                log_event("Sesion", "Cierre cancelado", seccion=name)
                self.show_page(name, source="cierre cancelado")
                return
        self.close()

    def close(self, exit_process: bool = True) -> None:
        """
        Cierra rapido y sin ver como se desarma la ventana: un fundido breve, se
        oculta y recien entonces se liberan documentos y widgets. Al salir del
        proceso no se destruyen los widgets uno por uno (era la demora visible):
        el sistema libera todo al terminar.
        """
        self._closing = True
        self._remember_geometry()
        duration = timedelta(seconds=round(time.monotonic() - self._started))
        log_event("Sesion", "Fin de la sesion", duracion=duration, tareas_pendientes=self.runner.pending)
        self.fade(1.0, 0.0, CLOSE_FADE_MS)
        self.root.withdraw()
        for page in self.pages.values():
            page.on_close()
        self.runner.shutdown()
        self.appearance.uninstall()
        if exit_process:
            logging.shutdown()  # vuelca los registros antes de salir
            os._exit(0)
        self.root.destroy()

    def _remember_geometry(self) -> None:
        maximized = self.root.state() == "zoomed"
        self.settings.window_maximized = maximized
        if not maximized:
            # CTk guarda el tamano sin escalar en estos atributos.
            self.settings.window_width = int(getattr(self.root, "_current_width", self.root.winfo_width()))
            self.settings.window_height = int(getattr(self.root, "_current_height", self.root.winfo_height()))
        self.save_settings()


def _prune_scaling_callbacks() -> None:
    """
    CustomTkinter guarda un aviso de escala por widget y no siempre lo quita al
    destruirlo (p. ej. el menu interno de un CTkOptionMenu de una ventana ya
    cerrada): al cambiar la escala, ese aviso fallaba con "invalid command
    name". Se descartan los de ventanas y widgets que ya no existen.
    """
    tracker = ctk.ScalingTracker
    for window in list(tracker.window_widgets_dict):
        try:
            alive = bool(window.winfo_exists())
        except tk.TclError:
            alive = False
        if not alive:
            tracker.window_widgets_dict.pop(window, None)
            tracker.window_dpi_scaling_dict.pop(window, None)
            continue
        callbacks = tracker.window_widgets_dict[window]
        callbacks[:] = [callback for callback in callbacks if _widget_alive(getattr(callback, "__self__", None))]


def _widget_alive(widget) -> bool:
    if widget is None or not hasattr(widget, "winfo_exists"):
        return True  # no es un widget: se deja como esta
    try:
        return bool(widget.winfo_exists())
    except tk.TclError:
        return False


def _show(value: object) -> str:
    """Valor legible en el registro (cadenas vacias incluidas)."""
    if value == "":
        return "(vacio)"
    if isinstance(value, bool):
        return "si" if value else "no"
    return str(value)
