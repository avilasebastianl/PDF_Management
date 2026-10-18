"""
Seccion Herramientas: comprimir, dividir, numerar y marca de agua desde la
interfaz (las operaciones corren en segundo plano). Requiere pantalla.
"""

import pymupdf
from conftest import make_pdf, page_texts, pump

from pdfmanagement.gui.pages import tools as tools_page


def run(gui_app, page):
    page._run()
    pump(gui_app, lambda: not gui_app.runner.busy, timeout=0.5)
    pump(gui_app, timeout=0.2)


def open_tools(gui_app, tmp_path, pages=4):
    gui_app.show_page("Herramientas")
    page = gui_app.pages["Herramientas"]
    page.tool.set(tools_page.COMPRESS)  # la ventana se comparte entre pruebas: estado conocido
    page._show_tool(tools_page.COMPRESS, log=False)
    source = make_pdf(tmp_path / "informe.pdf", pages)
    page.source_field.set(source)
    pump(gui_app, timeout=0.1)
    return page, source


def test_tools_section_is_registered(gui_app):
    assert "Herramientas" in gui_app.nav_buttons
    gui_app.show_page("Herramientas")
    page = gui_app.pages["Herramientas"]
    assert page.tool.cget("values") == list(tools_page.TOOLS)


def test_number_pages_from_the_interface(gui_app, tmp_path):
    page, _source = open_tools(gui_app, tmp_path)
    page.tool.set(tools_page.NUMBER)
    page._show_tool(tools_page.NUMBER)
    assert page.output_field.path.name == "informe_numerado.pdf"
    page.template.set("{n}/{total}")
    run(gui_app, page)
    output = page.output_field.path
    assert output.exists() and "1/4" in page_texts(output)[0]
    assert gui_app.status_bar.state == "success"


def test_split_shows_folder_and_writes_parts(gui_app, tmp_path):
    page, _source = open_tools(gui_app, tmp_path, pages=5)
    page.tool.set(tools_page.SPLIT)
    page._show_tool(tools_page.SPLIT)
    assert page.folder_row.winfo_manager() == "grid"
    page.folder.set(str(tmp_path / "partes"))
    page.split_mode.set(next(label for label, key in tools_page.SPLIT_MODES.items() if key == "cada"))
    page._on_split_mode(page.split_mode.get())
    page.split_value.set("2")
    run(gui_app, page)
    parts = sorted((tmp_path / "partes").glob("*.pdf"))
    assert [len(page_texts(part)) for part in parts] == [2, 2, 1]


def test_compress_and_watermark(gui_app, tmp_path):
    page, _source = open_tools(gui_app, tmp_path)
    run(gui_app, page)  # Comprimir (por defecto)
    assert page.output_field.path.name == "informe_comprimido.pdf" and page.output_field.path.exists()
    page.tool.set(tools_page.WATERMARK)
    page._show_tool(tools_page.WATERMARK)
    page.mark_text.set("BORRADOR")
    run(gui_app, page)
    with pymupdf.open(page.output_field.path) as document:
        assert "BORRADOR" in document[0].get_text()


def test_watermark_preview_in_the_interface(gui_app, tmp_path):
    page, _source = open_tools(gui_app, tmp_path)
    page.tool.set(tools_page.WATERMARK)
    page._show_tool(tools_page.WATERMARK)
    page.refresh_preview()
    assert page._preview_image is not None, "con un PDF elegido se ve la primera pagina con la marca"
    page.orientation.set("Vertical")
    assert page.mark_angle == 90
    page.refresh_preview()
    assert page._preview_image is not None
