"""
Interfaz grafica (CustomTkinter). Toda la logica de PDFs vive en ``core``.
"""


def run_gui() -> None:
    """Carga las preferencias y abre la ventana principal."""
    from .. import i18n
    from ..config import Settings

    _set_app_id()
    settings = Settings.load()
    i18n.set_language(settings.language)  # antes de importar la interfaz: sus textos se traducen al cargarse
    from .app import MainWindow

    MainWindow(settings).run()


def _set_app_id() -> None:
    """
    En Windows, identifica el proceso como "PDF Management" y no como Python:
    asi la barra de tareas muestra el icono de la aplicacion (y la agrupa aparte).
    """
    import sys

    if sys.platform.startswith("win"):
        import ctypes

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PDFManagement.App")
        except (AttributeError, OSError):
            pass
