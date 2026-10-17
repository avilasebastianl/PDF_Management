"""
Registro de paginas: el orden de esta lista define la barra lateral y los
atajos Ctrl+1..N. Para agregar una funcionalidad basta con crear una subclase
de ``BasePage`` y anadirla aqui.
"""

from .base import BasePage
from .convert import ConvertPage
from .extract import ExtractPage
from .merge import MergePage
from .security import SecurityPage
from .settings import SettingsPage
from .sign import SignPage
from .viewer import ViewerPage

# El Visor va primero: es el centro de la aplicacion y desde el se envian documentos al resto.
PAGES: list[type[BasePage]] = [ViewerPage, MergePage, ExtractPage, ConvertPage, SignPage, SecurityPage, SettingsPage]


def page_names() -> list[str]:
    return [page.name for page in PAGES]
