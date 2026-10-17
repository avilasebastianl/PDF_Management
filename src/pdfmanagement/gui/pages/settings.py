"""
Pagina "Ajustes": apariencia, comportamiento y datos de la aplicacion.

Los cambios se guardan al instante. Solo el color del tema (limitacion de
CustomTkinter) y el idioma (los textos se traducen al cargar la interfaz)
requieren reiniciar.
"""

import webbrowser
from datetime import datetime
from tkinter import filedialog

import customtkinter as ctk

from ... import GITHUB_URL, LINKEDIN_URL, REPOSITORY_URL, __app_name__, __author__, __version__, logging_setup, paths
from ...config import APPEARANCE_MODES, UI_SCALING_OPTIONS, available_color_themes
from ...i18n import LANGUAGES, tr
from .. import style
from ..dropdown import dropdown_menu
from ..icons import icon
from ..system import open_path
from ..widgets import Card, ToolTip, field_label, hide, muted_label, primary_button, secondary_button, show
from .base import BasePage

MODE_LABELS = {"System": tr("Sistema"), "Light": tr("Claro"), "Dark": tr("Oscuro")}
# Nombre visible de cada tema de color (el valor guardado es el nombre del archivo en assets/themes).
COLOR_LABELS = {
    "AzulOscuro": tr("Azul oscuro"),
    "Lavanda": tr("Lavanda"),
    "Naranja": tr("Naranja"),
    "Rojo": tr("Rojo"),
    "Verde": tr("Verde"),
}
DEBUG_LOGGING_HELP = tr(
    "Registro detallado\n"
    "Guarda en log/app.log cada acción con más detalle (páginas del visor, zoom, posición "
    "de la firma, desplegables, tiempos internos). Útil para diagnosticar un problema; "
    "se aplica al instante, sin reiniciar. Las contraseñas nunca se registran."
)


SAVED_TITLE = tr("Los cambios se guardan automáticamente")
SAVED_DETAIL = tr(
    "No hace falta pulsar ningún botón: lo que elija aquí queda guardado al instante y será la "
    "configuración predeterminada cada vez que abra la aplicación."
)
SAVED_BANNER_BG = ("#eaf2fc", "#1d2733")
ABOUT_TAGLINE = tr("Sus PDFs, fáciles, gratis y 100 % privados")
ABOUT_BANNER_MUTED = ("gray90", "gray85")
ABOUT_AUTHOR_BG = ("gray90", "gray22")
ABOUT_WRAP = 400
ABOUT_STACK = ("Python", "CustomTkinter", "PyMuPDF", "pypdf", "pyHanko", "pytest")
ABOUT_PURPOSE = tr(
    "Resuelve las tareas más comunes con PDFs de forma fácil y gratuita, sin subir sus documentos "
    "a internet: todo se procesa en su equipo."
)
ABOUT_HIGHLIGHTS = (
    tr("100 % local y sin conexión: sus archivos nunca salen del equipo"),
    tr("Visor con pestañas para leer, buscar, anotar y organizar páginas"),
    tr("Firma visual y firma digital con certificado (PAdES)"),
    tr("Unir, extraer, convertir y proteger con AES-256"),
    tr("Nunca modifica el original: siempre «Guardar como», con deshacer ilimitado"),
)
ABOUT_HOW = tr(
    "Arquitectura por capas (núcleo sin interfaz, servicios y GUI) con pruebas automatizadas. "
    "Desarrollada con la asistencia de Claude Code (Anthropic)."
)


class SettingsPage(BasePage):
    name = "Ajustes"
    title = tr("Ajustes")
    subtitle = tr("Personalice la apariencia y el comportamiento de la aplicación.")
    icon_name = "settings"

    def build(self) -> None:
        self.body.grid_columnconfigure(0, weight=3)
        self.body.grid_columnconfigure(1, weight=2)
        self._build_saved_banner()

        # * Apariencia
        appearance = Card(self.body, tr("Apariencia"))
        appearance.grid(row=1, column=0, sticky="new", padx=(0, style.GAP), pady=(0, style.GAP))
        self.mode = ctk.CTkSegmentedButton(
            appearance,
            values=[MODE_LABELS[mode] for mode in APPEARANCE_MODES],
            command=self._on_mode_changed,
            font=style.fonts().body,
        )
        self._row(appearance, 0, tr("Modo"), self.mode)

        self._color_labels = {theme: COLOR_LABELS.get(theme, theme) for theme in available_color_themes()}
        self.color = dropdown_menu(appearance, list(self._color_labels.values()), self._on_color_changed)
        self._row(appearance, 1, tr("Color de acento"), self.color)

        self.scaling = dropdown_menu(
            appearance, [f"{int(value * 100)}%" for value in UI_SCALING_OPTIONS], self._on_scaling_changed
        )
        self._row(appearance, 2, tr("Tamaño de la interfaz"), self.scaling)

        # Cada idioma se muestra en su propio nombre: se reconoce aunque la interfaz este en otro.
        self.language = dropdown_menu(appearance, list(LANGUAGES.values()), self._on_language_changed)
        self._row(appearance, 3, tr("Idioma"), self.language)

        self.restart_notice = ctk.CTkFrame(appearance, fg_color="transparent")
        muted_label(self.restart_notice, tr("Los cambios de color e idioma se aplicarán al reiniciar.")).pack(
            side="left"
        )
        primary_button(self.restart_notice, tr("Reiniciar ahora"), self.app.restart, "refresh", width=150).pack(
            side="left", padx=10
        )
        self.restart_notice.grid(
            row=appearance.row(4), column=0, columnspan=3, sticky="w", padx=style.CARD_PAD, pady=(6, 0)
        )
        hide(self.restart_notice)

        # * General
        general = Card(self.body, tr("General"))
        general.grid(row=2, column=0, sticky="new", padx=(0, style.GAP), pady=(0, style.GAP))
        # Se muestran los nombres traducidos; se guarda el identificador interno de la seccion.
        from .registry import page_label  # aqui y no arriba: registry importa esta pagina

        self._page_labels = {name: page_label(name) for name in self.app.nav_buttons}
        self.initial_page = dropdown_menu(general, list(self._page_labels.values()), self._on_initial_page)
        self._row(general, 0, tr("Página inicial"), self.initial_page)

        self.open_after = ctk.CTkSwitch(general, text="", command=self._on_open_after)
        self._row(general, 1, tr("Abrir el archivo al terminar"), self.open_after)

        field_label(general, tr("Carpeta de salida")).grid(
            row=general.row(2), column=0, sticky="w", padx=(style.CARD_PAD, style.GAP), pady=(8, 0)
        )
        self.output_dir = muted_label(general)
        self.output_dir.grid(row=general.row(2), column=1, sticky="ew", padx=(0, style.CARD_PAD), pady=(8, 0))
        buttons = ctk.CTkFrame(general, fg_color="transparent")
        buttons.grid(row=general.row(3), column=1, sticky="w", pady=(6, 0))
        secondary_button(buttons, tr("Cambiar"), self._choose_output_dir, "folder", width=110).pack(side="left")
        secondary_button(buttons, tr("Restablecer"), self._reset_output_dir, width=110).pack(side="left", padx=8)

        # * Datos
        data = Card(
            self.body,
            tr("Datos locales"),
            tr("Todo se procesa y guarda en este equipo; la aplicación no usa internet."),
        )
        data.grid(row=3, column=0, sticky="new", padx=(0, style.GAP), pady=(0, style.PAD))
        folders = ctk.CTkFrame(data, fg_color="transparent")
        folders.grid(row=data.row(0), column=0, columnspan=3, sticky="w", padx=style.CARD_PAD, pady=(10, 0))
        for logged, text, folder in (
            ("Salida", tr("Salida"), lambda: self.app.settings.output_path),
            ("Firmas", tr("Firmas"), lambda: paths.SIGNATURES_DIR),
            ("Registros", tr("Registros"), lambda: paths.LOG_DIR),
        ):
            secondary_button(
                folders,
                text,
                lambda f=folder, t=logged: self._open_folder(f(), t),
                "folder",
                width=110,
            ).pack(side="left", padx=(0, 8))

        diagnostics = ctk.CTkFrame(data, fg_color="transparent")
        diagnostics.grid(row=data.row(1), column=0, columnspan=3, sticky="w", padx=style.CARD_PAD, pady=(12, 0))
        self.debug_switch = ctk.CTkSwitch(
            diagnostics,
            text=tr("Registro detallado (para depurar)"),
            font=style.fonts().body,
            command=self._on_debug_logging,
        )
        self.debug_switch.pack(side="left")
        ToolTip(self.debug_switch, DEBUG_LOGGING_HELP)
        secondary_button(diagnostics, tr("Ver registro"), self._open_log, "open", width=120).pack(
            side="left", padx=(12, 0)
        )

        self._build_about()

    def _build_saved_banner(self) -> None:
        """Aviso fijo: todo se guarda al instante y queda como configuracion al iniciar."""
        accent = style.accent_color()
        banner = ctk.CTkFrame(
            self.body, corner_radius=style.CORNER, fg_color=SAVED_BANNER_BG, border_width=1, border_color=accent
        )
        banner.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, style.GAP))
        banner.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(banner, text="", image=icon("check", 22, accent)).grid(
            row=0, column=0, rowspan=2, padx=(16, 12), pady=12
        )
        ctk.CTkLabel(banner, text=SAVED_TITLE, font=style.fonts().body_bold, text_color=style.TEXT, anchor="w").grid(
            row=0, column=1, sticky="w", pady=(10, 0)
        )
        muted_label(banner, SAVED_DETAIL, wraplength=640).grid(row=1, column=1, sticky="w", pady=(0, 10))
        self.saved_status = ctk.CTkLabel(banner, text="", font=style.fonts().small, text_color=style.TEXT_MUTED)
        self.saved_status.grid(row=0, column=2, rowspan=2, padx=16)
        self.app.settings_listeners.append(self._on_settings_saved)

    def _on_settings_saved(self, changed: list[str]) -> None:
        """Confirma cada guardado ("Guardado a las 10:42") y lo resalta un momento."""
        if not changed or not self.saved_status.winfo_exists():
            return
        self.saved_status.configure(
            text=tr("✓ Guardado a las {hora}", hora=f"{datetime.now():%H:%M:%S}"), text_color=style.accent_color()
        )
        fade: str | None = getattr(self, "_saved_fade", None)
        if fade:
            self.after_cancel(fade)
        self._saved_fade = self.after(2500, lambda: self.saved_status.configure(text_color=style.TEXT_MUTED))

    def _build_about(self) -> None:
        """Tarjeta destacada: proposito, ventajas, como se hizo y quien la desarrollo."""
        accent = style.accent_color()
        about = self.about = ctk.CTkFrame(
            self.body, corner_radius=style.CORNER, fg_color=style.CARD_BG, border_width=2, border_color=accent
        )
        about.grid(row=1, column=1, rowspan=4, sticky="new", pady=(0, style.PAD))
        about.grid_columnconfigure(0, weight=1)
        # La fila vacia de abajo absorbe el alto extra: las tarjetas de la izquierda no se separan.
        self.body.grid_rowconfigure(4, weight=1)

        # Cabecera con el color de acento: logo, nombre y eslogan.
        banner = ctk.CTkFrame(about, corner_radius=style.CORNER - 2, fg_color=accent)
        banner.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
        ctk.CTkLabel(banner, text="", image=icon("pdf", 48, style.WHITE)).grid(
            row=0, column=0, rowspan=3, padx=(18, 12), pady=14
        )
        ctk.CTkLabel(banner, text=__app_name__, font=style.fonts().title, text_color=style.WHITE, anchor="w").grid(
            row=0, column=1, sticky="w", pady=(14, 0)
        )
        ctk.CTkLabel(banner, text=ABOUT_TAGLINE, font=style.fonts().body, text_color=style.WHITE, anchor="w").grid(
            row=1, column=1, sticky="w"
        )
        ctk.CTkLabel(
            banner,
            text=tr("Versión {version}  ·  Licencia Apache 2.0", version=__version__),
            font=style.fonts().small,
            text_color=ABOUT_BANNER_MUTED,
            anchor="w",
        ).grid(row=2, column=1, sticky="w", pady=(2, 14))

        body = ctk.CTkFrame(about, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=style.CARD_PAD + 2, pady=(14, style.CARD_PAD))
        body.grid_columnconfigure(0, weight=1)
        row = iter(range(100))
        ctk.CTkLabel(
            body,
            text=ABOUT_PURPOSE,
            font=style.fonts().body,
            text_color=style.TEXT,
            justify="left",
            anchor="w",
            wraplength=ABOUT_WRAP,
        ).grid(row=next(row), column=0, sticky="w")

        self._about_title(body, tr("En qué se destaca"), next(row))
        check = icon("check", 18, accent)
        for item in ABOUT_HIGHLIGHTS:
            line = ctk.CTkFrame(body, fg_color="transparent")
            line.grid(row=next(row), column=0, sticky="w", pady=2)
            ctk.CTkLabel(line, text="", image=check, width=20).pack(side="left", anchor="n", padx=(0, 6))
            ctk.CTkLabel(
                line,
                text=item,
                font=style.fonts().body,
                text_color=style.TEXT,
                justify="left",
                anchor="w",
                wraplength=ABOUT_WRAP - 30,
            ).pack(side="left")

        self._about_title(body, tr("Cómo se hizo"), next(row))
        muted_label(body, ABOUT_HOW, wraplength=ABOUT_WRAP).grid(row=next(row), column=0, sticky="w")
        chips = ctk.CTkFrame(body, fg_color="transparent")
        chips.grid(row=next(row), column=0, sticky="w", pady=(8, 0))
        for index, technology in enumerate(ABOUT_STACK):
            ctk.CTkLabel(
                chips,
                text=technology,
                font=style.fonts().small,
                fg_color=style.HOVER,
                corner_radius=10,
                text_color=style.TEXT,
                height=24,
            ).grid(row=index // 4, column=index % 4, padx=(0, 6), pady=3, ipadx=8, sticky="w")

        # Autor: bloque resaltado con sus enlaces.
        author = ctk.CTkFrame(body, corner_radius=10, fg_color=ABOUT_AUTHOR_BG)
        author.grid(row=next(row), column=0, sticky="ew", pady=(18, 0))
        muted_label(author, tr("Desarrollado por")).pack(anchor="w", padx=14, pady=(12, 0))
        ctk.CTkLabel(author, text=__author__, font=style.fonts().section, text_color=style.TEXT, anchor="w").pack(
            anchor="w", padx=14
        )
        links = ctk.CTkFrame(author, fg_color="transparent")
        links.pack(anchor="w", padx=14, pady=(10, 14))
        for text, url, make in (
            ("GitHub", GITHUB_URL, primary_button),
            ("LinkedIn", LINKEDIN_URL, primary_button),
            (tr("Código fuente"), REPOSITORY_URL, secondary_button),
        ):
            button = make(links, text, lambda link=url: self._open_link(link), "open", width=108)
            button.pack(side="left", padx=(0, 8))
            ToolTip(button, url.removeprefix("https://"))

    @staticmethod
    def _about_title(parent, text: str, row: int) -> None:
        ctk.CTkLabel(parent, text=text, font=style.fonts().section, text_color=style.TEXT, anchor="w").grid(
            row=row, column=0, sticky="w", pady=(16, 6)
        )

    def _open_link(self, url: str) -> None:
        """Abre el enlace en el navegador (la aplicacion en si nunca se conecta a internet)."""
        self.log("Enlace abierto: %s", url)
        webbrowser.open(url)

    def _row(self, card: Card, offset: int, label: str, widget) -> None:
        field_label(card, label).grid(
            row=card.row(offset), column=0, sticky="w", padx=(style.CARD_PAD, style.GAP), pady=8
        )
        widget.grid(row=card.row(offset), column=1, sticky="w", pady=8, padx=(0, style.CARD_PAD))

    def on_show(self) -> None:
        settings = self.app.settings
        snapshot = (
            settings.appearance_mode,
            settings.color_theme,
            settings.ui_scaling,
            settings.language,
            settings.initial_page,
            settings.open_after_save,
            str(settings.output_path),
            settings.debug_logging,
        )
        if snapshot == getattr(self, "_shown", None):
            return  # nada cambio desde la ultima vez: evita redibujar los controles
        self._shown = snapshot
        self.mode.set(MODE_LABELS[settings.appearance_mode])
        self.color.set(self._color_labels.get(settings.color_theme, settings.color_theme))
        self.scaling.set(f"{round(settings.ui_scaling * 100)}%")
        self.language.set(LANGUAGES.get(settings.language, LANGUAGES["es"]))
        self.initial_page.set(self._page_labels.get(settings.initial_page, settings.initial_page))
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

    def _on_color_changed(self, label: str) -> None:
        self.app.settings.color_theme = next(
            (theme for theme, shown in self._color_labels.items() if shown == label), label
        )
        self.app.save_settings()
        show(self.restart_notice)

    def _on_scaling_changed(self, label: str) -> None:
        self.app.set_ui_scaling(int(label.rstrip("%")) / 100)

    def _on_language_changed(self, label: str) -> None:
        code = next((code for code, shown in LANGUAGES.items() if shown == label), None)
        if code is None or code == self.app.settings.language:
            return
        self.app.settings.language = code
        self.app.save_settings()
        show(self.restart_notice)

    def _on_initial_page(self, label: str) -> None:
        self.app.settings.initial_page = next(
            (name for name, shown in self._page_labels.items() if shown == label), label
        )
        self.app.save_settings()

    def _on_open_after(self) -> None:
        self.app.settings.open_after_save = bool(self.open_after.get())
        self.app.save_settings()

    def _choose_output_dir(self) -> None:
        chosen = filedialog.askdirectory(title=tr("Carpeta de salida"), initialdir=str(self.app.settings.output_path))
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
