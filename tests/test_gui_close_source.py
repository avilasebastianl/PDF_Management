"""Boton "Cerrar" del archivo de origen en las secciones (ademas de Examinar). Requiere pantalla."""

import pytest
from conftest import make_pdf, pump


@pytest.mark.parametrize("section", ["Firmar", "Proteger", "Herramientas", "Extraer"])
def test_close_button_resets_the_section(gui_app, tmp_path, section):
    gui_app.show_page(section)
    page = gui_app.pages[section]
    field = page.source_field
    assert field.close_button is not None and not field.close_button.winfo_manager(), "sin archivo no se ve"
    field.set(make_pdf(tmp_path / "doc.pdf", 2))
    pump(gui_app, timeout=0.3)
    assert field.close_button.winfo_manager() == "pack", "con un archivo aparece Cerrar"
    field.close_button.invoke()
    pump(gui_app, timeout=0.2)
    assert field.path is None and not field.close_button.winfo_manager()
    assert page.source_info.cget("text") == "" if hasattr(page, "source_info") else True
    if hasattr(page, "output_field") and page.output_field.auto:
        assert page.output_field.get() == "", "el nombre de salida automatico se vacia"
    if section == "Firmar":
        assert page.document is None and page.view.document is None, "el visor de Firmar queda vacio"


def test_convert_has_the_close_button(gui_app):
    gui_app.show_page("Convertir")
    assert gui_app.pages["Convertir"].source_field.close_button is not None
