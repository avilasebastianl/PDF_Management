"""Documentos nuevos en blanco o desde plantilla (core/create.py)."""

import pymupdf
import pytest

from pdfmanagement import core
from pdfmanagement.core import create


@pytest.mark.parametrize("template", create.TEMPLATES)
def test_every_template_builds(template):
    document = create.build_document(create.NewDocument(template, "A4", False, 3))
    try:
        expected = 3 if template in create.MULTI_PAGE else 1
        assert document.page_count == expected
        assert (document[0].rect.width, document[0].rect.height) == (595, 842)
        if template in ("letter", "minutes", "invoice"):
            assert document[0].get_text().strip(), "las plantillas con formulario tienen sus rotulos"
    finally:
        document.close()


def test_size_orientation_and_file(tmp_path):
    output = create.create_document(tmp_path / "nuevo.pdf", create.NewDocument("grid", "Carta", True, 2))
    with pymupdf.open(output) as document:
        assert document.page_count == 2
        assert (document[0].rect.width, document[0].rect.height) == (792, 612)


def test_cyrillic_labels_are_readable():
    document = pymupdf.open()
    page = document.new_page()
    create._write(page, (72, 72), "Акт совещания", 14, (0, 0, 0), bold=True)
    assert "Акт совещания" in page.get_text().replace("\xa0", " ")
    document.close()


@pytest.mark.parametrize(
    "spec",
    [
        create.NewDocument("poster"),
        create.NewDocument("blank", "A0"),
        create.NewDocument("blank", pages=0),
        create.NewDocument("blank", pages=create.MAX_PAGES + 1),
    ],
)
def test_invalid_requests(spec):
    with pytest.raises(core.InvalidInputError):
        create.build_document(spec)
