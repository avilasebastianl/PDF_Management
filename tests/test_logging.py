"""
Registro (logging): formato, modo detallado, eventos de la interfaz y que las
contrasenas nunca queden escritas.
"""

import logging

import pytest

from conftest import pump
from pdfmanagement import logging_setup
from pdfmanagement.gui import events


@pytest.fixture
def configured_log(tmp_path, monkeypatch):
    """Registro real escribiendo en una carpeta temporal."""
    monkeypatch.delenv(logging_setup.DEBUG_ENV_VAR, raising=False)
    logging_setup.configure_logging(tmp_path / "log")
    yield tmp_path / "log" / "app.log"
    logger = logging.getLogger(logging_setup.ROOT_LOGGER)
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    logger.setLevel(logging.NOTSET)


def test_file_format_has_milliseconds_thread_and_short_name(configured_log):
    events.log_event("Unir", "Agregados %d archivos", 2, total=2)
    line = configured_log.read_text(encoding="utf-8").strip().splitlines()[-1]
    assert line.startswith("[") and "." in line.split("]")[0]  # milisegundos
    assert "MainThread" in line
    assert "gui.events: [Unir] Agregados 2 archivos  | total=2" in line


def test_debug_mode_can_be_toggled_at_runtime(configured_log):
    events.debug_event("Firmar", "zoom oculto")
    logging_setup.set_debug(True)
    assert logging_setup.is_debug()
    events.debug_event("Firmar", "zoom visible")
    logging_setup.set_debug(False)
    events.debug_event("Firmar", "zoom oculto otra vez")
    text = configured_log.read_text(encoding="utf-8")
    assert "zoom visible" in text
    assert "zoom oculto" not in text


def test_debug_mode_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv(logging_setup.DEBUG_ENV_VAR, "1")
    try:
        logging_setup.configure_logging(tmp_path / "log")
        assert logging_setup.is_debug()
    finally:
        logger = logging.getLogger(logging_setup.ROOT_LOGGER)
        for handler in list(logger.handlers):
            handler.close()
            logger.removeHandler(handler)
        logger.setLevel(logging.NOTSET)


def test_passwords_are_redacted_and_events_fit_in_one_line(caplog):
    caplog.set_level(logging.INFO, logger="pdfmanagement")
    events.log_event("Proteger", "Aviso:\nlinea 1\nlinea 2", password="secreta", clave_origen="", archivo="a.pdf")
    [record] = caplog.records
    message = record.getMessage()
    assert "secreta" not in message
    assert "password=***" in message and "clave_origen=(vacia)" in message
    assert "\n" not in message and "Aviso: / linea 1 / linea 2" in message


def test_describe_files_shortens_long_lists():
    assert events.describe_files([f"doc_{index}.pdf" for index in range(8)], limit=3) == "doc_0.pdf, doc_1.pdf, doc_2.pdf (+5 mas)"


# * Eventos de la interfaz (requiere pantalla) -------------------------------

def test_gui_logs_navigation_settings_and_tasks(gui_app, caplog, pdf_factory):
    caplog.set_level(logging.DEBUG, logger="pdfmanagement")
    gui_app.show_page("Ajustes")
    gui_app.show_page("Unir", source="atajo Ctrl+1")
    previous_page = gui_app.settings.initial_page
    gui_app.settings.initial_page = "Firmar" if previous_page != "Firmar" else "Unir"
    gui_app.save_settings()

    merge = gui_app.pages["Unir"]
    merge._clear()
    merge._add_files([pdf_factory("uno.pdf", 1), pdf_factory("dos.pdf", 1)])
    pump(gui_app, lambda: not gui_app.runner.busy and not merge._rows_to_build)
    merge._move(0, 1)

    messages = [record.getMessage() for record in caplog.records]
    assert any("[Navegacion] Unir -> Ajustes" in m or "-> Ajustes" in m for m in messages)
    assert any("[Navegacion] Ajustes -> Unir" in m and "origen=atajo Ctrl+1" in m for m in messages)
    assert any(f"[Ajustes] Pagina inicial: {previous_page} -> " in m for m in messages)
    assert any("[Unir] Agregados 2 archivos: uno.pdf, dos.pdf" in m for m in messages)
    assert any("[Unir] Movido uno.pdf: posicion 1 -> 2" in m for m in messages)
    assert any(m.startswith("Tarea #") and "Leyendo 2 PDFs" in m and "terminada" in m for m in messages)


def test_gui_never_logs_passwords(gui_app, caplog, pdf_factory):
    caplog.set_level(logging.DEBUG, logger="pdfmanagement")
    gui_app.show_page("Proteger")
    page = gui_app.pages["Proteger"]
    page.source_field.set(pdf_factory("secreto.pdf", 1))
    page.mode.set("Proteger con contrasena")
    page._apply_mode()
    page.password.set("clave-ultra-secreta")
    page.confirmation.set("clave-ultra-secreta")
    page._run()
    pump(gui_app, lambda: not gui_app.runner.busy)
    assert "clave-ultra-secreta" not in caplog.text
    assert "Protegiendo PDF solicitado: secreto.pdf" in caplog.text
