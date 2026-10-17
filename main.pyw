"""
Punto de entrada de PDF Management.

Doble clic (pythonw) abre la interfaz grafica. Desde una terminal:
``python main.pyw --help`` lista los comandos disponibles.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from pdfmanagement.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
