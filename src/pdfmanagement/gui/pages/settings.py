"""
Pagina "Ajustes": apariencia, comportamiento y datos de la aplicacion.

Los cambios se guardan al instante. Solo el color del tema requiere reiniciar
(limitacion de CustomTkinter).
"""

from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

from ... import __app_name__, __version__, logging_setup, paths
from ...config import APPEARANCE_MODES, UI_SCALING_OPTIONS, available_color_themes
from .. import style
from ..dropdown import dropdown_menu
from ..system import open_path
from ..widgets import Card, ToolTip, field_label, hide, muted_label, primary_button, secondary_button, show
from .base import BasePage

MODE_LABELS = {"System": "Sistema", "Light": "Claro", "Dark": "Oscuro"}
DEBUG_LOGGING_HELP = (
    "Registro detallado\n"
    "Guarda en log/app.log cada accion con mas detalle (paginas del visor, zoom, posicion "
    "de la firma, desplegables, tiempos internos). Util para diagnosticar un problema; "
    "se aplica al instante, sin reiniciar. Las contrasenas nunca se registran."
)


class SettingsPage(BasePage):
    name = "Ajustes"
    title = "Ajustes"
    subtitle = "Personalice la apariencia y el comportamiento. Los cambios se guardan automaticamente."
    icon_name = "settings"

    def build(self) -> None:
        settings = self.app.settings
        self.body.grid_columnconfigure(0, weight=3)
        self.body.grid_columnconfigure(1, weight=2)

        # * Apariencia
        appearance = Card(self.body, "Apariencia")
        appearance.grid(row=0, column=0, sticky="new", padx=(0, style.GAP), pady=(0, style.GAP))
        self.mode = ctk.CTkSegmentedButton(
            appearance, values=[MODE_LABELS[mode] for mode in APPEARANCE_MODES],
            command=self._on_mode_changed, font=style.fonts().body,
        )
        self._row(appearance, 0, "Modo", self.mode)

        self.color = dropdown_menu(appearance, available_color_themes(), self._on_color_changed)
        self._row(appearance, 1, "Color de acento", self.color)

        self.scaling = dropdown_menu(
            appearance, [f"{int(value * 100)}%" for value in UI_SCALING_OPTIONS], self._on_scaling_changed
        )
        self._row(appearance, 2, "Tamano de la interfaz", self.scaling)

        self.restart_notice = ctk.CTkFrame(appearance, fg_color="transparent")
        muted_label(self.restart_notice, "El nuevo color se aplicara al reiniciar.").pack(side="left")
        primary_button(self.restart_notice, "Reiniciar ahora", self.app.restart, "refresh", width=150).pack(side="left", padx=10)
        self.restart_notice.grid(row=appearance.row(3), column=0, columnspan=3, sticky="w", padx=style.CARD_PAD, pady=(6, 0))
        hide(self.restart_notice)

        # * General
        general = Card(self.body, "General")
        general.grid(row=1, column=0, sticky="new", padx=(0, style.GAP), pady=(0, style.GAP))
        self.initial_page = dropdown_menu(general, list(self.app.nav_buttons), self._on_initial_page)
        self._row(general, 0, "Pagina inicial", self.initial_page)

        self.open_after = ctk.CTkSwitch(general, text="", command=self._on_open_after)
        self._row(general, 1, "Abrir el archivo al terminar", self.open_after)

        field_label(general, "Carpeta de salida").grid(row=general.row(2), column=0, sticky="w", padx=(style.CARD_PAD, style.GAP), pady=(8, 0))
        self.output_dir = muted_label(general)
        self.output_dir.grid(row=general.row(2), column=1, sticky="ew", padx=(0, style.CARD_PAD), pady=(8, 0))
        buttons = ctk.CTkFrame(general, fg_color="transparent")
        buttons.grid(row=general.row(3), column=1, sticky="w", pady=(6, 0))
        secondary_button(buttons, "Cambiar", self._choose_output_dir, "folder", width=110).pack(side="left")
        secondary_button(buttons, "Restablecer", self._reset_output_dir, width=110).pack(side="left", padx=8)

        # * Datos
        data = Card(self.body, "Datos locales", "Todo se procesa y guarda en este equipo; la aplicacion no usa internet.")
        data.grid(row=2, column=0, sticky="new", padx=(0, style.GAP), pady=(0, style.PAD))
        folders = ctk.CTkFrame(data, fg_color="transparent")
        folders.grid(row=data.row(0), column=0, columnspan=3, sticky="w", padx=style.CARD_PAD, pady=(10, 0))
        for text, folder in (
            ("Salida", lambda: self.app.settings.output_path),
            ("Firmas", lambda: paths.SIGNATURES_DIR),
            ("Registros", lambda: paths.LOG_DIR),
        ):
            secondary_button(
                folders, text, lambda f=folder, t=text: self._open_folder(f(), t), "folder", width=110,
            ).pack(side="left", padx=(0, 8))

        diagnostics = ctk.CTkFrame(data, fg_color="transparent")
        diagnostics.grid(row=data.row(1), column=0, columnspan=3, sticky="w", padx=style.CARD_PAD, pady=(12, 0))
        self.debug_switch = ctk.CTkSwitch(
            diagnostics, text="Registro detallado (para depurar)", font=style.fonts().body,
            command=self._on_debug_logging,
        )
        self.debug_switch.pack(side="left")
        ToolTip(self.debug_switch, DEBUG_LOGGING_HELP)
        secondary_button(diagnostics, "Ver registro", self._open_log, "open", width=120).pack(side="left", padx=(12, 0))

        # * Acerca de
        about = Card(self.body, "Acerca de")
        about.grid(row=0, column=1, rowspan=3, sticky="new", pady=(0, style.PAD))
        ctk.CTkLabel(about, text=__app_name__, font=style.fonts().section).grid(
            row=about.row(0), column=0, columnspan=3, sticky="w", padx=style.CARD_PAD, pady=(6, 0)
        )
        muted_label(about, f"Version {__version__}  ·  Licencia Apache 2.0").grid(
            row=about.row(1), column=0, columnspan=3, sticky="w", padx=style.CARD_PAD
        )
        muted_label(
            about, "Herramienta gratuita y 100% local para unir, extraer, convertir, firmar y proteger PDFs.",
            wraplength=300,
        ).grid(row=about.row(2), column=0, columnspan=3, sticky="w", padx=style.CARD_PAD, pady=(8, 0))
        if paths.DONATION_QR.exists():
            ctk.CTkLabel(about, text="Apoye el proyecto", font=style.fonts().body_bold).grid(
                row=about.row(3), column=0, columnspan=3, sticky="w", padx=style.CARD_PAD, pady=(16, 6)
            )
            qr = Image.open(paths.DONATION_QR)
            qr.thumbnail((180, 180))
            self._qr_image = ctk.CTkImage(qr, qr, size=qr.size)
            ctk.CTkLabel(about, text="", image=self._qr_image).grid(
                row=about.row(4), column=0, columnspan=3, padx=style.CARD_PAD, pady=(0, 4)
            )

    def _row(self, card: Card, offset: int, label: str, widget) -> None:
        field_label(card, label).grid(row=card.row(offset), column=0, sticky="w", padx=(style.CARD_PAD, style.GAP), pady=8)
        widget.grid(row=card.row(offset), column=1, sticky="w", pady=8, padx=(0, style.CARD_PAD))

    def on_show(self) -> None:
        settings = self.app.settings
        snapshot = (
            settings.appearance_mode, settings.color_theme, settings.ui_scaling,
            settings.initial_page, settings.open_after_save, str(settings.output_path), settings.debug_logging,
        )
        if snapshot == getattr(self, "_shown", None):
            return  # nada cambio desde la ultima vez: evita redibujar los controles
        self._shown = snapshot
        self.mode.set(MODE_LABELS[settings.appearance_mode])
        self.color.set(settings.color_theme)
        self.scaling.set(f"{int(round(settings.ui_scaling * 100))}%")
        self.initial_page.set(settings.initial_page)
        if settings.open_after_save:
            self.open_after.select()
        else:
            self.open_after.deselect()
        self.output_dir.configure(text=str(settings.output_path))
        if settings.debug_logging:
            self.debug_switch.select()
        else:
            self.debug_switch.deselect()

    # * Eventos -------------------------------------------------------------

    def _on_mode_changed(self, label: str) -> None:
        mode = next(key for key, value in MODE_LABELS.items() if value == label)
        self.app.set_appearance_mode(mode)

    def _on_color_changed(self, color: str) -> None:
        self.app.settings.color_theme = color
        self.app.save_settings()
        show(self.restart_notice)

    def _on_scaling_changed(self, label: str) -> None:
        self.app.set_ui_scaling(int(label.rstrip("%")) / 100)

    def _on_initial_page(self, name: str) -> None:
        self.app.settings.initial_page = name
        self.app.save_settings()

    def _on_open_after(self) -> None:
        self.app.settings.open_after_save = bool(self.open_after.get())
        self.app.save_settings()

    def _choose_output_dir(self) -> None:
        chosen = filedialog.askdirectory(title="Carpeta de salida", initialdir=str(self.app.settings.output_path))
        if not chosen:
            self.log_debug("Carpeta de salida: dialogo cancelado")
        if chosen:
            self.app.settings.output_dir = chosen
            self.app.save_settings()
            self.on_show()

    def _reset_output_dir(self) -> None:
        self.app.settings.output_dir = ""
        self.app.save_settings()
        self.on_show()

    def _open_folder(self, folder, label: str) -> None:
        self.log("Carpeta abierta: %s", label, ruta=folder)
        folder.mkdir(parents=True, exist_ok=True)
        open_path(folder)

    def _on_debug_logging(self) -> None:
        self.app.set_debug_logging(bool(self.debug_switch.get()))

    def _open_log(self) -> None:
        log_file = logging_setup.app_log_file()
        self.log("Registro abierto", archivo=log_file)
        open_path(log_file)
