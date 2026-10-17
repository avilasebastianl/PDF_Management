"""
Traducciones de la interfaz: espanol (original), ingles y ruso.

Los textos se escriben en espanol, con sus tildes, y ese texto es la clave:

    tr("Guardar como")                          -> "Save as" en ingles
    tr("Página {n} de {total}", n=3, total=9)   -> "Page 3 of 9"
    trn("{count} página", "{count} páginas", 4) -> "4 pages" / "4 страницы"

Los catalogos (``assets/locales/<codigo>.json``) asocian cada texto a su
traduccion; los plurales tienen una lista con las formas del idioma (ingles:
una y otra; ruso: una, pocas y muchas). Si falta una traduccion se muestra el
espanol. ``tests/test_i18n.py`` comprueba que los catalogos esten completos.

El idioma se fija al arrancar (``set_language``) antes de construir la
interfaz; cambiarlo requiere reiniciar, igual que el color de acento.

Se usa ``tr`` y no el clasico ``_`` porque ``_`` ya se usa como variable
descartable y podria taparlo sin querer.
"""

import json
import logging
from typing import Any

from . import paths

logger = logging.getLogger(__name__)

LANGUAGES = {"es": "Español", "en": "English", "ru": "Русский"}
DEFAULT_LANGUAGE = "es"
LOCALES_DIR = paths.ASSETS_DIR / "locales"

_language = DEFAULT_LANGUAGE
_catalog: dict[str, Any] = {}


def set_language(code: str) -> str:
    """Activa el idioma ``code`` (si no existe, espanol). Devuelve el que quedo activo."""
    global _language, _catalog
    if code not in LANGUAGES:
        logger.warning("Idioma desconocido %r: se usa espanol", code)
        code = DEFAULT_LANGUAGE
    catalog: dict[str, Any] = {}
    if code != DEFAULT_LANGUAGE:
        catalog = load_catalog(code)
    _language, _catalog = code, catalog
    return code


def load_catalog(code: str) -> dict[str, Any]:
    path = LOCALES_DIR / f"{code}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        logger.error("No se pudo cargar el idioma %s (%s): se usa espanol", code, error)
        return {}


def language() -> str:
    return _language


def tr(text: str, /, **values: Any) -> str:
    """Texto traducido; ``values`` rellena los ``{marcadores}``."""
    translated = _catalog.get(text, text)
    if not isinstance(translated, str):
        translated = text
    return translated.format(**values) if values else translated


def trn(singular: str, plural: str, count: int, /, **values: Any) -> str:
    """Texto con plural segun ``count`` (disponible como ``{count}``)."""
    forms = _catalog.get(singular)
    if isinstance(forms, list) and forms:
        text = forms[min(plural_form(_language, count), len(forms) - 1)]
    else:
        text = singular if count == 1 else plural
    return text.format(count=count, **values)


def plural_form(code: str, count: int) -> int:
    """Indice de la forma plural de ``count`` en el idioma ``code``."""
    count = abs(count)
    if code == "ru":
        if count % 10 == 1 and count % 100 != 11:
            return 0
        if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
            return 1
        return 2
    return 0 if count == 1 else 1
