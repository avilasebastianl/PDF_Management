"""Terminaciones de un PDF: marca de agua y firma (core/finish.py), como en Unir."""

import pymupdf
import pytest
from conftest import CERTIFICATE_PASSWORD, make_pdf
from PIL import Image, ImageDraw

from pdfmanagement import core
from pdfmanagement.core import finish, verify


@pytest.fixture
def signature_image(tmp_path):
    path = tmp_path / "firma.png"
    image = Image.new("RGB", (300, 120), "white")
    ImageDraw.Draw(image).line((20, 90, 280, 30), fill="black", width=8)
    image.save(path)
    return path


def test_watermark_and_visual_signature_on_the_last_page(tmp_path, signature_image):
    pdf = make_pdf(tmp_path / "unido.pdf", 3)
    finish.apply_finish(
        pdf,
        watermark=finish.WatermarkOptions("BORRADOR", opacity=0.3, angle=0),
        signature=finish.SignatureOptions("visual", position="abajo-derecha", pages="ultima", image=signature_image),
    )
    with pymupdf.open(pdf) as document:
        assert all("BORRADOR" in page.get_text() for page in document)
        assert [len(page.get_image_info()) for page in document] == [0, 0, 1], "firma solo en la ultima"
        [info] = document[2].get_image_info()
        assert info["bbox"][0] > document[2].rect.width / 2 and info["bbox"][3] > document[2].rect.height / 2


def test_visual_signature_on_every_page(tmp_path, signature_image):
    pdf = make_pdf(tmp_path / "unido.pdf", 2)
    finish.apply_finish(pdf, signature=finish.SignatureOptions("visual", pages="todas", image=signature_image))
    with pymupdf.open(pdf) as document:
        assert [len(page.get_image_info()) for page in document] == [1, 1]


def test_digital_signature_is_valid_and_last(tmp_path, certificate):
    pdf = make_pdf(tmp_path / "unido.pdf", 2)
    finish.apply_finish(
        pdf,
        watermark=finish.WatermarkOptions("COPIA"),
        signature=finish.SignatureOptions(
            "digital", pages="primera", certificate=certificate[0], certificate_password=CERTIFICATE_PASSWORD
        ),
    )
    [report] = verify.verify_signatures(pdf)
    assert report.intact and report.valid and not report.modified_after, "la marca va antes de firmar"


def test_preview_shows_watermark_and_signature(tmp_path, signature_image):
    pdf = make_pdf(tmp_path / "unido.pdf", 2)
    plain = finish.preview(pdf, 1, height=300)
    finished = finish.preview(
        pdf,
        1,
        height=300,
        watermark=finish.WatermarkOptions("BORRADOR", opacity=0.5),
        signature=finish.SignatureOptions("visual", image=signature_image),
    )
    digital = finish.preview(pdf, 1, height=300, signature=finish.SignatureOptions("digital"))
    assert plain.height == 300 and plain.tobytes() != finished.tobytes() != digital.tobytes()
    with pymupdf.open(pdf) as document:
        assert "BORRADOR" not in document[0].get_text(), "la vista previa no modifica el archivo"


def test_missing_signature_inputs(tmp_path):
    pdf = make_pdf(tmp_path / "unido.pdf", 1)
    with pytest.raises(core.InvalidInputError):
        finish.apply_finish(pdf, signature=finish.SignatureOptions("visual"))
    with pytest.raises(core.InvalidInputError):
        finish.apply_finish(pdf, signature=finish.SignatureOptions("digital"))
