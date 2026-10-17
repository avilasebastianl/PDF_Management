"""
Pruebas de la firma digital con certificado (PAdES B-B) usando un certificado
autofirmado generado al vuelo y validando el resultado con pyHanko.
"""

import pymupdf
import pytest
from asn1crypto import x509 as asn1_x509
from conftest import CERTIFICATE_PASSWORD, make_certificate, page_texts
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko_certvalidator import ValidationContext

from pdfmanagement import core


def validate(pdf_path, certificate_der):
    """Valida todas las firmas del PDF confiando solo en el certificado de prueba."""
    with open(pdf_path, "rb") as stream:
        reader = PdfFileReader(stream, strict=False)
        context = ValidationContext(trust_roots=[asn1_x509.Certificate.load(certificate_der)], allow_fetching=False)
        return [validate_pdf_signature(signature, context) for signature in reader.embedded_signatures]


def sign(source, output, certificate, **kwargs):
    return core.sign_pdf_with_certificate(source, output, certificate[0], CERTIFICATE_PASSWORD, **kwargs)


def signature_widget_rect(pdf_path, page_index):
    """Recuadro de la firma tal como se ve (coordenadas de pantalla)."""
    with pymupdf.open(pdf_path) as document:
        page = document[page_index]
        widgets = [widget for widget in page.widgets() if widget.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE]
        assert len(widgets) == 1
        return widgets[0].rect * page.rotation_matrix


# * Firma valida ---------------------------------------------------------------


def test_signed_pdf_validates(pdf_factory, tmp_path, certificate):
    source = pdf_factory("contrato.pdf", 2)
    result = sign(source, tmp_path / "firmado.pdf", certificate, reason="Aprobacion", location="Bogota")

    [status] = validate(result, certificate[1])
    assert status.intact and status.valid and status.trusted
    assert status.bottom_line
    assert status.signing_cert.subject.native["common_name"] == "Firmante de Prueba"
    with open(result, "rb") as stream:
        [embedded] = PdfFileReader(stream, strict=False).embedded_signatures
        assert embedded.sig_object["/SubFilter"] == "/ETSI.CAdES.detached"
        assert embedded.sig_object["/Reason"] == "Aprobacion"
        assert embedded.sig_object["/Location"] == "Bogota"
    assert page_texts(result) == page_texts(source)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_visible_signature_matches_viewer(pdf_factory, tmp_path, certificate, signature_png, rotation):
    source = pdf_factory("a.pdf", 3, rotation=rotation)
    placement = core.SignaturePlacement(x=100, y=200, width=180, page_number=2)
    result = sign(source, tmp_path / "firmado.pdf", certificate, placement=placement, signature_image=signature_png)

    [status] = validate(result, certificate[1])
    assert status.bottom_line
    with pymupdf.open(source) as document:
        page_rect = document[1].rect
    aspect = core.digital_aspect_ratio(core.image_aspect_ratio(core.load_signature(signature_png)))
    expected = core.signature_rect(page_rect, placement, aspect)
    actual = signature_widget_rect(result, 1)
    assert actual.x0 == pytest.approx(expected.x0, abs=0.5)
    assert actual.y0 == pytest.approx(expected.y0, abs=0.5)
    assert actual.width == pytest.approx(expected.width, abs=0.5)
    assert actual.height == pytest.approx(expected.height, abs=0.5)


def test_visible_signature_is_drawn_upright_on_rotated_page(pdf_factory, tmp_path, certificate, signature_png):
    """La imagen debe quedar en la parte superior del recuadro y la leyenda debajo, como en el visor."""
    source = pdf_factory("a.pdf", 1, rotation=90)
    placement = core.SignaturePlacement(x=100, y=100, width=200)
    result = sign(source, tmp_path / "firmado.pdf", certificate, placement=placement, signature_image=signature_png)

    rect = signature_widget_rect(result, 0)
    with pymupdf.open(result) as document:
        pixmap = document[0].get_pixmap(clip=rect, dpi=72)
    image_part = pymupdf.Rect(0, 0, pixmap.width, pixmap.height * 0.5)
    rows = [y for y in range(pixmap.height) if any(pixmap.pixel(x, y)[0] < 40 for x in range(pixmap.width))]
    # El trazo negro (relleno solido de la firma de prueba) ocupa la mitad superior.
    assert rows and min(rows) < image_part.y1 and max(rows) > image_part.y1 * 0.5


def test_text_only_signature_without_image(pdf_factory, tmp_path, certificate):
    source = pdf_factory("a.pdf", 1)
    placement = core.SignaturePlacement(x=50, y=50, width=200)
    result = sign(source, tmp_path / "firmado.pdf", certificate, placement=placement)
    assert validate(result, certificate[1])[0].bottom_line
    rect = signature_widget_rect(result, 0)
    assert rect.height == pytest.approx(200 * core.digital_aspect_ratio(None), abs=0.5)


def test_multiple_signatures_remain_valid(pdf_factory, tmp_path, certificate):
    second_certificate = make_certificate(tmp_path / "segundo.p12", name="Segundo Firmante")
    first = sign(pdf_factory("a.pdf", 1), tmp_path / "una.pdf", certificate)
    both = core.sign_pdf_with_certificate(
        first,
        tmp_path / "dos.pdf",
        second_certificate[0],
        CERTIFICATE_PASSWORD,
        placement=core.SignaturePlacement(x=50, y=50),
    )
    (first_status,) = validate(both, certificate[1])[:1]
    second_status = validate(both, second_certificate[1])[1]
    assert first_status.intact and first_status.valid
    assert second_status.bottom_line


def test_sign_encrypted_pdf(pdf_factory, tmp_path, certificate):
    locked = core.lock_pdf(pdf_factory("a.pdf", 2), tmp_path / "locked.pdf", "secreta")
    with pytest.raises(core.PasswordRequiredError):
        sign(locked, tmp_path / "firmado.pdf", certificate)
    with pytest.raises(core.WrongPasswordError):
        sign(locked, tmp_path / "firmado.pdf", certificate, password="mala")

    result = sign(
        locked, tmp_path / "firmado.pdf", certificate, password="secreta", placement=core.SignaturePlacement(x=50, y=50)
    )
    assert core.get_pdf_info(result).encrypted
    texts = page_texts(result, "secreta")
    assert texts[0] == "Pagina 1"
    assert texts[1].startswith("Pagina 2") and "Firmante de Prueba" in texts[1]


# * Modificaciones posteriores --------------------------------------------------


def test_tampering_after_signing_breaks_integrity(pdf_factory, tmp_path, certificate):
    result = sign(pdf_factory("a.pdf", 1), tmp_path / "firmado.pdf", certificate)
    data = bytearray(result.read_bytes())
    # El texto "Pagina 1" esta en hexadecimal en el contenido; se cambia a "Pagina 9".
    original = b"Pagina 1".hex().encode()
    position = data.index(original)
    data[position : position + len(original)] = b"Pagina 9".hex().encode()
    result.write_bytes(bytes(data))

    [status] = validate(result, certificate[1])
    assert not status.intact
    assert not status.bottom_line


def test_editing_after_signing_is_detected(pdf_factory, tmp_path, certificate):
    result = sign(pdf_factory("a.pdf", 1), tmp_path / "firmado.pdf", certificate)
    with pymupdf.open(result) as document:
        document[0].insert_text((72, 300), "Texto agregado despues de firmar")
        document.saveIncr()

    [status] = validate(result, certificate[1])
    assert status.intact  # los bytes firmados no cambiaron...
    assert not status.bottom_line  # ...pero el cambio posterior invalida la firma


# * Errores ---------------------------------------------------------------------


def test_wrong_certificate_password(pdf_factory, tmp_path, certificate):
    source = pdf_factory("a.pdf", 1)
    output = tmp_path / "salida" / "firmado.pdf"
    with pytest.raises(core.WrongCertificatePasswordError) as raised:
        core.sign_pdf_with_certificate(source, output, certificate[0], "incorrecta")
    assert "no es correcta" in str(raised.value)
    assert not output.exists()
    with pytest.raises(core.WrongCertificatePasswordError):
        core.load_certificate(certificate[0], None)


def test_load_certificate_info(certificate):
    info = core.load_certificate(certificate[0], CERTIFICATE_PASSWORD)
    assert info.subject == "Firmante de Prueba"
    assert info.self_signed


def test_certificate_without_password(pdf_factory, tmp_path):
    unprotected = make_certificate(tmp_path / "libre.pfx", password=None)
    result = core.sign_pdf_with_certificate(pdf_factory("a.pdf", 1), tmp_path / "firmado.pdf", unprotected[0], None)
    assert validate(result, unprotected[1])[0].bottom_line


def test_expired_certificate_is_rejected(pdf_factory, tmp_path):
    expired = make_certificate(tmp_path / "vencido.p12", valid_days=(-30, -1))
    with pytest.raises(core.CertificateError, match="vencio"):
        core.sign_pdf_with_certificate(pdf_factory("a.pdf", 1), tmp_path / "out.pdf", expired[0], CERTIFICATE_PASSWORD)


def test_invalid_certificate_file(pdf_factory, tmp_path):
    fake = tmp_path / "falso.pfx"
    fake.write_bytes(b"esto no es un certificado")
    with pytest.raises(core.CertificateError, match="no es un certificado"):
        core.load_certificate(fake, "x")
    with pytest.raises(core.InvalidInputError):
        core.load_certificate(pdf_factory("a.pdf", 1), "x")


def test_all_pages_is_rejected(pdf_factory, tmp_path, certificate):
    placement = core.SignaturePlacement(x=10, y=10, all_pages=True)
    with pytest.raises(core.InvalidInputError, match="una sola pagina"):
        sign(pdf_factory("a.pdf", 2), tmp_path / "out.pdf", certificate, placement=placement)
