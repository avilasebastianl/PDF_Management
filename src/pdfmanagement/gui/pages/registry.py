"""
Registro de paginas: el orden de esta lista define la barra lateral y los
atajos Ctrl+1..N. Para agregar una funcionalidad basta con crear una subclase
de ``BasePage`` y anadirla aqui.
"""

from ...i18n import tr
from .base import BasePage
from .convert import ConvertPage
from .extract import ExtractPage
from .merge import MergePage
from .organize import OrganizePage
from .security import SecurityPage
from .settings import SettingsPage
from .sign import SignPage
from .tools import ToolsPage
from .viewer import ViewerPage

# El Visor va primero: es el centro de la aplicacion y desde el se envian documentos al resto.
PAGES: list[type[BasePage]] = [
    ViewerPage,
    MergePage,
    OrganizePage,
    ExtractPage,
    ConvertPage,
    SignPage,
    SecurityPage,
    ToolsPage,
    SettingsPage,
]

# Nombres visibles de las secciones. ``name`` es el identificador interno (ajustes, registro,
# pruebas) y no se traduce; en pantalla se muestra traducido. Los literales alimentan los catalogos.
PAGE_LABELS = {
    "Visor": tr("Visor"),
    "Unir": tr("Unir"),
    "Organizar": tr("Organizar"),
    "Extraer": tr("Extraer"),
    "Convertir": tr("Convertir"),
    "Firmar": tr("Firmar"),
    "Proteger": tr("Proteger"),
    "Herramientas": tr("Herramientas"),
    "Ajustes": tr("Ajustes"),
}


def page_names() -> list[str]:
    return [page.name for page in PAGES]


def page_label(name: str) -> str:
    """Nombre traducido de la seccion ``name`` (identificador interno)."""
    return PAGE_LABELS.get(name) or tr(name)
