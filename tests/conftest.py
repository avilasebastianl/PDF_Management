"""
Fixtures compartidas: PDFs e imagenes generados al vuelo en una carpeta temporal.
"""

import sys
from pathlib import Path

import pymupdf
import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def make_pdf(path: Path, pages: int, *, rotation: int = 0, width: float = 595, height: float = 842) -> Path:
    """Crea un PDF cuyo texto en cada pagina es ``Pagina N``."""
    document = pymupdf.open()
    for number in range(1, pages + 1):
        page = document.new_page(width=width, height=height)
        page.insert_text((72, 72), f"Pagina {number}", fontsize=20)
        if rotation:
            page.set_rotation(rotation)
    document.save(path)
    document.close()
    return path


def page_texts(path: Path, password: str | None = None) -> list[str]:
    with pymupdf.open(path) as document:
        if password:
            document.authenticate(password)
        return [page.get_text().strip() for page in document]


@pytest.fixture
def pdf_factory(tmp_path):
    def factory(name: str = "doc.pdf", pages: int = 3, **kwargs) -> Path:
        return make_pdf(tmp_path / name, pages, **kwargs)

    return factory


@pytest.fixture
def signature_png(tmp_path) -> Path:
    """Firma con fondo transparente y margenes vacios (200x100, trazo en el centro)."""
    image = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle((50, 25, 149, 74), fill=(0, 0, 0, 255))
    path = tmp_path / "firma.png"
    image.save(path)
    return path


@pytest.fixture
def signature_jpg(tmp_path) -> Path:
    """Firma escaneada: fondo blanco opaco."""
    image = Image.new("RGB", (300, 100), "white")
    ImageDraw.Draw(image).line((20, 50, 280, 50), fill="black", width=8)
    path = tmp_path / "firma.jpg"
    image.save(path)
    return path
