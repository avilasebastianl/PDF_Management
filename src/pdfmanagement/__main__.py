"""Permite ejecutar ``python -m pdfmanagement`` desde la carpeta ``src``."""

import sys

from .cli import main

sys.exit(main())
