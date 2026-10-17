"""Verificacion de firmas digitales existentes (core/verify.py)."""

import pymupdf
import pytest
from conftest import CERTIFICATE_PASSWORD, make_pdf

from pdfmanagement import core
from pdfmanagement.core import verify


def sign(source, output, certificate):
    return core.sign_pdf_with_certificate(source, output, certificate[0], CERTIFICATE_PASSWORD)


def test_unsigned_document_has_no_signatures(tmp_path):
    assert verify.verify_signatures(make_pdf(tmp_path / "plano.pdf", 1)) == []


def test_self_signed_signature_is_correct_but_identity_unverified(tmp_path, certificate):
    signed = sign(make_pdf(tmp_path / "a.pdf", 1), tmp_path / "firmado.pdf", certificate)
    [report] = verify.verify_signatures(signed)
    assert report.intact and report.valid and not report.modified_after
    assert report.state == verify.UNTRUSTED and "Firmante de Prueba" in report.signer
    assert report.signed_at is not None
    assert "identidad" in report.summary


def test_editing_after_signing_is_reported(tmp_path, certificate):
    signed = sign(make_pdf(tmp_path / "a.pdf", 1), tmp_path / "firmado.pdf", certificate)
    with pymupdf.open(signed) as document:
        document[0].insert_text((72, 300), "Agregado despues")
        document.saveIncr()
    [report] = verify.verify_signatures(signed)
    assert report.intact and report.state == verify.MODIFIED


def test_tampered_bytes_break_the_signature(tmp_path, certificate):
    signed = sign(make_pdf(tmp_path / "a.pdf", 1), tmp_path / "firmado.pdf", certificate)
    data = bytearray(signed.read_bytes())
    original = b"Pagina 1".hex().encode()
    position = data.index(original)
    data[position : position + len(original)] = b"Pagina 9".hex().encode()
    signed.write_bytes(bytes(data))
    [report] = verify.verify_signatures(signed)
    assert report.state == verify.BROKEN


def test_two_signatures_are_listed_in_order(tmp_path, certificate):
    first = sign(make_pdf(tmp_path / "a.pdf", 1), tmp_path / "uno.pdf", certificate)
    second = sign(first, tmp_path / "dos.pdf", certificate)
    reports = verify.verify_signatures(second)
    assert len(reports) == 2 and all(report.valid for report in reports)
    assert reports[0].field != reports[1].field


def test_protected_signed_pdf_needs_password(tmp_path, certificate):
    locked = core.lock_pdf(make_pdf(tmp_path / "a.pdf", 1), tmp_path / "protegido.pdf", "clave123")
    signed = core.sign_pdf_with_certificate(
        locked, tmp_path / "firmado.pdf", certificate[0], CERTIFICATE_PASSWORD, password="clave123"
    )
    with pytest.raises(core.PasswordRequiredError):
        verify.verify_signatures(signed)
    [report] = verify.verify_signatures(signed, "clave123")
    assert report.valid
