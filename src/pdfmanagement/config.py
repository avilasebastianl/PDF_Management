"""
Preferencias del usuario.

Se guardan en ``config/settings.ini``. Si el archivo no existe se crea con los
valores por defecto; si contiene valores invalidos se corrigen al cargarlo, de
modo que la aplicacion siempre arranca. Tambien migra el formato anterior
(``config/default.ini``).
"""

import configparser
import logging
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from . import paths

logger = logging.getLogger(__name__)

APPEARANCE_MODES = ("System", "Light", "Dark")
UI_SCALING_OPTIONS = (0.8, 0.9, 1.0, 1.1, 1.25, 1.5)
DEFAULT_COLOR_THEME = "AzulOscuro"

# Clave -> (seccion actual, (seccion, opcion) del formato anterior)
_LAYOUT: dict[str, tuple[str, tuple[str, str] | None]] = {
    "window_width": ("Window", ("Size", "width")),
    "window_height": ("Window", ("Size", "height")),
    "window_maximized": ("Window", None),
    "appearance_mode": ("Appearance", ("Theme", "theme")),
    "color_theme": ("Appearance", ("Theme", "color_theme")),
    "ui_scaling": ("Appearance", ("Display", "ui_scaling")),
    "initial_page": ("General", ("App", "initial_window")),
    "open_after_save": ("General", ("Display", "open_after_save")),
    "output_dir": ("General", None),
}

# Nombres de pestanas usados por versiones anteriores.
_LEGACY_PAGES = {
    "Unificar PDFs": "Unir",
    "Desunir PDF": "Extraer",
    "Transformar a PDF": "Convertir",
    "Firmar PDF": "Firmar",
    "Seguridad PDF": "Proteger",
    "Configuraciones": "Ajustes",
}


def available_color_themes() -> list[str]:
    """Temas de color disponibles en ``assets/themes``."""
    return sorted(theme.stem for theme in paths.THEMES_DIR.glob("*.json"))


@dataclass
class Settings:
    """Preferencias persistentes. Los nombres de campo son las claves del .ini."""

    window_width: int = 1180
    window_height: int = 760
    window_maximized: bool = False
    appearance_mode: str = "System"
    color_theme: str = DEFAULT_COLOR_THEME
    ui_scaling: float = 1.0
    initial_page: str = "Unir"
    open_after_save: bool = True
    output_dir: str = ""

    @property
    def output_path(self) -> Path:
        """Carpeta de salida por defecto (``export/`` si no se configuro otra)."""
        return Path(self.output_dir) if self.output_dir else paths.EXPORT_DIR

    @classmethod
    def load(cls, settings_file: Path = paths.SETTINGS_FILE) -> "Settings":
        """Carga las preferencias, migrando el formato anterior si es necesario."""
        parser = configparser.ConfigParser()
        source = settings_file
        if not settings_file.exists() and paths.LEGACY_SETTINGS_FILE.exists():
            source = paths.LEGACY_SETTINGS_FILE
            logger.info("Migrando preferencias desde %s", source.name)
        try:
            parser.read(source, encoding="utf-8")
        except configparser.Error as error:
            logger.warning("Preferencias ilegibles, se usan valores por defecto: %s", error)

        settings = cls()
        for field in fields(cls):
            raw = _read_option(parser, field.name)
            if raw is None:
                continue
            try:
                setattr(settings, field.name, _convert(raw, type(getattr(settings, field.name))))
            except ValueError:
                logger.warning("Valor invalido para %s: %r", field.name, raw)

        settings._normalize()
        if not settings_file.exists():
            settings.save(settings_file)
        return settings

    def save(self, settings_file: Path = paths.SETTINGS_FILE) -> None:
        """Escribe las preferencias en disco."""
        self._normalize()
        parser = configparser.ConfigParser()
        for key, value in asdict(self).items():
            section = _LAYOUT[key][0]
            if not parser.has_section(section):
                parser.add_section(section)
            parser.set(section, key, _serialize(value))
        settings_file.parent.mkdir(parents=True, exist_ok=True)
        with settings_file.open("w", encoding="utf-8") as file:
            parser.write(file)

    def _normalize(self) -> None:
        defaults = Settings()
        self.window_width = max(900, min(self.window_width, 3840))
        self.window_height = max(600, min(self.window_height, 2160))
        if self.appearance_mode.capitalize() in APPEARANCE_MODES:
            self.appearance_mode = self.appearance_mode.capitalize()
        else:
            self.appearance_mode = defaults.appearance_mode
        if self.color_theme not in available_color_themes():
            self.color_theme = DEFAULT_COLOR_THEME
        self.ui_scaling = max(0.75, min(round(self.ui_scaling, 2), 2.0))
        self.initial_page = _LEGACY_PAGES.get(self.initial_page, self.initial_page)


def _read_option(parser: configparser.ConfigParser, key: str) -> str | None:
    section, legacy = _LAYOUT[key]
    if parser.has_option(section, key):
        return parser.get(section, key)
    if legacy and parser.has_option(*legacy):
        return parser.get(*legacy)
    return None


def _convert(raw: str, target: type) -> object:
    raw = raw.strip()
    if target is bool:
        return raw.lower() in ("1", "true", "yes", "si", "sí", "on")
    if target is int:
        return int(float(raw))
    if target is float:
        return float(raw)
    return raw


def _serialize(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)
