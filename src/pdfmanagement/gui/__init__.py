"""
Interfaz grafica (CustomTkinter). Toda la logica de PDFs vive en ``core``.
"""


def run_gui() -> None:
    """Carga las preferencias y abre la ventana principal."""
    from ..config import Settings
    from .app import MainWindow

    MainWindow(Settings.load()).run()
