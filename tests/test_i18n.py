"""
Traducciones: el mecanismo (plurales, marcadores, idioma desconocido) y que
los catalogos de ingles y ruso tengan todos los textos de la interfaz.
"""

import ast
import json
import re
import string
from pathlib import Path

import pytest

from pdfmanagement import i18n

SRC = Path(__file__).resolve().parents[1] / "src" / "pdfmanagement"


def source_messages() -> dict[str, str]:
    """
    Textos pasados a tr()/trn() en el codigo: {texto: archivo:linea}. De trn se
    toma el singular, que es la clave (su valor es la lista de formas).
    """
    found: dict[str, str] = {}
    for path in SRC.rglob("*.py"):
        if "_vendor" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("tr", "trn"):
                argument = node.args[0] if node.args else None
                if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                    found.setdefault(argument.value, f"{path.name}:{node.lineno}")
    return found


def placeholders(text: str) -> set[str]:
    return {name for _literal, name, _spec, _conv in string.Formatter().parse(text) if name}


@pytest.fixture(autouse=True)
def _restore_language():
    yield
    i18n.set_language("es")


def test_translation_falls_back_to_spanish_and_formats():
    i18n.set_language("es")
    assert i18n.tr("Página {n} de {total}", n=2, total=5) == "Página 2 de 5"
    assert i18n.set_language("xx") == "es"


def test_plural_rules():
    assert [i18n.plural_form("ru", n) for n in (1, 2, 5, 11, 21, 22, 25)] == [0, 1, 2, 2, 0, 1, 2]
    assert [i18n.plural_form("en", n) for n in (0, 1, 2)] == [1, 0, 1]
    i18n.set_language("es")
    assert i18n.trn("{count} página", "{count} páginas", 1) == "1 página"
    assert i18n.trn("{count} página", "{count} páginas", 3) == "3 páginas"


@pytest.mark.parametrize("code", ["en", "ru"])
def test_catalog_is_complete_and_consistent(code):
    catalog = json.loads((i18n.LOCALES_DIR / f"{code}.json").read_text(encoding="utf-8"))
    messages = source_messages()
    missing = {text: where for text, where in messages.items() if text not in catalog}
    assert not missing, f"faltan {len(missing)} traducciones ({code}): {list(missing.items())[:8]}"
    for text, translated in catalog.items():
        forms = translated if isinstance(translated, list) else [translated]
        for form in forms:
            assert placeholders(form) <= placeholders(text) | {"count"}, f"{code}: marcadores distintos en {text!r}"
            assert form.strip(), f"{code}: traduccion vacia de {text!r}"
    plurals = [value for value in catalog.values() if isinstance(value, list)]
    assert all(len(value) == (3 if code == "ru" else 2) for value in plurals), "formas de plural del idioma"


def test_language_switch_translates():
    i18n.set_language("en")
    catalog = json.loads((i18n.LOCALES_DIR / "en.json").read_text(encoding="utf-8"))
    sample = next((key for key, value in catalog.items() if isinstance(value, str)), None)
    if sample:
        assert i18n.tr(sample) == catalog[sample]


def test_no_unwrapped_accentless_ui_words():
    """Los textos de la interfaz llevan tildes (antes: 'Pagina', 'Codigo', 'Contrasena')."""
    pattern = re.compile(r"\b(Pagina|Codigo|Contrasena|contrasena|Tamano|pagina inicial)\b")
    offenders = [f"{text!r} ({where})" for text, where in source_messages().items() if pattern.search(text)]
    assert not offenders, offenders[:10]


@pytest.mark.parametrize("code", ["en", "ru"])
def test_translated_guide_has_the_linked_sections(code):
    """Firmar enlaza a una seccion de la guia por su titulo traducido: debe existir en esa guia."""
    guide = SRC.parents[1] / "docs" / f"user_guide.{code}.md"
    catalog = json.loads((i18n.LOCALES_DIR / f"{code}.json").read_text(encoding="utf-8"))
    headings = {
        line.lstrip("#").strip() for line in guide.read_text(encoding="utf-8").splitlines() if line.startswith("#")
    }
    assert catalog["Cómo obtener un certificado digital"] in headings
