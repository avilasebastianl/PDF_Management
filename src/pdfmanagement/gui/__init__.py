"""
Interfaz grafica (CustomTkinter). Toda la logica de PDFs vive en ``core``.
"""


def run_gui() -> None:
    """Carga las preferencias y abre la ventana principal."""
    from .. import i18n
    from ..config import Settings

    settings = Settings.load()
    i18n.set_language(settings.language)  # antes de importar la interfaz: sus textos se traducen al cargarse
    from .app import MainWindow

    MainWindow(settings).run()
