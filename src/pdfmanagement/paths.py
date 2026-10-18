"""
Rutas de la aplicacion.

- Recursos (solo lectura, versionados): ``assets/`` y ``docs/``.
- Datos del usuario (se crean al iniciar, ignorados por git): ``config/``,
  ``log/``, ``signs/`` y ``export/``.

Si la app se empaqueta con PyInstaller, los recursos se leen del paquete y los
datos se guardan junto al ejecutable. Cambiar ``DATA_DIR`` (por ejemplo a
``%APPDATA%``) basta para mover todos los datos del usuario.
"""

import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    DATA_DIR = Path(sys.executable).parent
else:
    RESOURCE_DIR = Path(__file__).resolve().parents[2]
    DATA_DIR = RESOURCE_DIR

# * Recursos
ASSETS_DIR = RESOURCE_DIR / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
THEMES_DIR = ASSETS_DIR / "themes"
DOCS_DIR = RESOURCE_DIR / "docs"
USER_GUIDE_FILE = DOCS_DIR / "user_guide.md"
APP_ICON = ICONS_DIR / "app.ico"  # generado desde app.png (varios tamanos)
APP_LOGO = ICONS_DIR / "app.png"
GITHUB_ICON = ICONS_DIR / "github.ico"
LINKEDIN_ICON = ICONS_DIR / "linkedin.ico"
CODE_ICON = ICONS_DIR / "code.ico"

# * Datos del usuario
CONFIG_DIR = DATA_DIR / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.ini"
LEGACY_SETTINGS_FILE = CONFIG_DIR / "default.ini"
LOG_DIR = DATA_DIR / "log"
SIGNATURES_DIR = DATA_DIR / "signs"
EXPORT_DIR = DATA_DIR / "export"


def ensure_data_dirs() -> None:
    """Crea las carpetas de datos del usuario si no existen."""
    for directory in (CONFIG_DIR, LOG_DIR, SIGNATURES_DIR, EXPORT_DIR):
        directory.mkdir(parents=True, exist_ok=True)
