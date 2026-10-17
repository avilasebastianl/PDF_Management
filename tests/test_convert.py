"""
Conversion real con Microsoft Office. Se omite si Office no esta instalado.
"""

import sys
import zipfile

import pytest

from conftest import page_texts
from pdfmanagement import core


def _office_available(prog_id: str) -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        from comtypes import GUID

        GUID.from_progid(prog_id)
        return True
    except (ImportError, OSError):
        return False


requires_word = pytest.mark.skipif(not _office_available("Word.Application"), reason="Microsoft Word no instalado")
requires_excel = pytest.mark.skipif(not _office_available("Excel.Application"), reason="Microsoft Excel no instalado")


def _minimal_docx(path, text: str):
    with zipfile.ZipFile(path, "w") as docx:
        docx.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        docx.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>",
        )
        docx.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>",
        )
    return path


@requires_word
def test_convert_docx(tmp_path):
    source = _minimal_docx(tmp_path / "carta.docx", "Hola desde Word")
    result = core.convert_to_pdf(source, tmp_path / "carta.pdf")
    assert page_texts(result) == ["Hola desde Word"]


@requires_excel
def test_convert_xlsx(tmp_path):
    import comtypes
    import comtypes.client

    source = tmp_path / "datos.xlsx"
    comtypes.CoInitialize()
    excel = comtypes.client.CreateObject("Excel.Application")
    try:
        excel.DisplayAlerts = False
        workbook = excel.Workbooks.Add()
        workbook.Worksheets(1).Range("A1").Value2 = "Hola desde Excel"
        workbook.SaveAs(str(source), 51)  # xlOpenXMLWorkbook
        workbook.Close(False)
    finally:
        excel.Quit()
        comtypes.CoUninitialize()

    result = core.convert_to_pdf(source, tmp_path / "datos.pdf")
    assert "Hola desde Excel" in page_texts(result)[0]


def test_convert_rejects_unsupported(tmp_path):
    source = tmp_path / "nota.txt"
    source.write_text("hola")
    with pytest.raises(core.InvalidInputError):
        core.convert_to_pdf(source, tmp_path / "nota.pdf")
