"""
Pruebas de preferencias (incluida la migracion del formato anterior) y de la CLI.
"""

import pytest
from conftest import CERTIFICATE_PASSWORD, page_texts

from pdfmanagement import cli, config, core, paths


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "LEGACY_SETTINGS_FILE", tmp_path / "default.ini")
    monkeypatch.setattr(paths, "LOG_DIR", tmp_path / "log")
    for name in ("CONFIG_DIR", "SIGNATURES_DIR", "EXPORT_DIR"):
        monkeypatch.setattr(paths, name, tmp_path / name.lower())
    return tmp_path


def test_settings_created_with_defaults(isolated_paths):
    settings_file = isolated_paths / "settings.ini"
    settings = config.Settings.load(settings_file)
    assert settings == config.Settings()
    assert settings_file.exists()


def test_settings_roundtrip_and_validation(isolated_paths):
    settings_file = isolated_paths / "settings.ini"
    settings = config.Settings(appearance_mode="dark", color_theme="Verde", ui_scaling=9, window_width=10)
    settings.save(settings_file)
    loaded = config.Settings.load(settings_file)
    assert loaded.appearance_mode == "Dark"
    assert loaded.color_theme == "Verde"
    assert loaded.ui_scaling == 2.0
    assert loaded.window_width == 900


def test_settings_migrates_legacy_file(isolated_paths):
    (isolated_paths / "default.ini").write_text(
        "[Size]\nwidth = 1400\nheight = 800\n[Theme]\ntheme = Light\ncolor_theme = Rojo\n"
        "[Display]\nui_scaling = 0.95\nopen_after_save = no\n[App]\ninitial_window = Firmar PDF\n",
        encoding="utf-8",
    )
    loaded = config.Settings.load(isolated_paths / "settings.ini")
    assert (loaded.window_width, loaded.window_height) == (1400, 800)
    assert (loaded.appearance_mode, loaded.color_theme) == ("Light", "Rojo")
    assert loaded.ui_scaling == 0.95
    assert loaded.open_after_save is False
    assert loaded.initial_page == "Firmar"


def test_settings_ignores_invalid_values(isolated_paths):
    settings_file = isolated_paths / "settings.ini"
    settings_file.write_text("[Window]\nwindow_width = mucho\n[Appearance]\ncolor_theme = red\n", encoding="utf-8")
    loaded = config.Settings.load(settings_file)
    assert loaded.window_width == config.Settings().window_width
    assert loaded.color_theme == config.DEFAULT_COLOR_THEME


def test_cli_extract_and_lock(isolated_paths, pdf_factory, tmp_path, capsys):
    source = pdf_factory("a.pdf", 3)
    output = tmp_path / "out.pdf"
    assert cli.main(["extract", str(source), "-p", "2-3", "-o", str(output)]) == 0
    assert page_texts(output) == ["Pagina 2", "Pagina 3"]

    locked = tmp_path / "locked.pdf"
    assert cli.main(["lock", str(output), "-o", str(locked), "--password", "clave123"]) == 0
    assert core.get_pdf_info(locked).encrypted
    assert "Archivo generado" in capsys.readouterr().out


def test_cli_reports_errors(isolated_paths, pdf_factory, tmp_path, capsys):
    source = pdf_factory("a.pdf", 2)
    assert cli.main(["extract", str(source), "-p", "9", "-o", str(tmp_path / "out.pdf")]) == 1
    assert "fuera de rango" in capsys.readouterr().err


def test_cli_sign_cert(isolated_paths, pdf_factory, tmp_path, certificate, signature_png, capsys):
    from pyhanko.pdf_utils.reader import PdfFileReader

    source = pdf_factory("a.pdf", 2)
    output = tmp_path / "firmado.pdf"
    arguments = ["sign-cert", str(source), "--cert", str(certificate[0]), "-o", str(output)]
    assert cli.main([*arguments, "--cert-password", "mala"]) == 1
    assert "no es correcta" in capsys.readouterr().err

    assert (
        cli.main(
            [
                *arguments,
                "--cert-password",
                CERTIFICATE_PASSWORD,
                "--image",
                str(signature_png),
                "--x",
                "100",
                "--y",
                "600",
                "--reason",
                "Aprobado",
            ]
        )
        == 0
    )
    with open(output, "rb") as stream:
        [signature] = PdfFileReader(stream, strict=False).embedded_signatures
        assert signature.sig_object["/Reason"] == "Aprobado"
        assert signature.sig_object.get_object()["/Contents"]
    assert "Archivo generado" in capsys.readouterr().out


def test_settings_app_icon_is_validated(isolated_paths):
    settings_file = isolated_paths / "settings.ini"
    config.Settings(app_icon="negro").save(settings_file)
    assert config.Settings.load(settings_file).app_icon == "negro"
    config.Settings(app_icon="inexistente").save(settings_file)
    assert config.Settings.load(settings_file).app_icon == "clasico"


def test_every_app_icon_variant_has_its_files():
    seen = set()
    for variant in paths.APP_ICON_VARIANTS:
        ico, png = paths.app_icon_files(variant)
        assert ico.exists() and png.exists(), variant
        seen.add(png)
    assert len(seen) == len(paths.APP_ICON_VARIANTS), "cada variante tiene su propia imagen"
    assert paths.app_icon_files("otra") == (paths.APP_ICON, paths.APP_LOGO)


def test_rename_signature(isolated_paths, signature_png):
    from pdfmanagement import signatures

    stored = signatures.import_signature(signature_png, "firma")
    renamed = signatures.rename_signature(stored, "Mi firma")
    assert renamed.name == "Mi_firma.png" and renamed.exists() and not stored.exists()
    assert signatures.rename_signature(renamed, "mi firma").name == "mi_firma.png", "solo mayusculas"
    other = signatures.import_signature(signature_png, "otra")
    assert signatures.rename_signature(other, "mi firma").name == "mi_firma_2.png", "no pisa otra firma"
    with pytest.raises(ValueError):
        signatures.rename_signature(other, "   ")
    with pytest.raises(ValueError):
        signatures.rename_signature(signature_png, "fuera")
