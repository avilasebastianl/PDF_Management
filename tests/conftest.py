"""
Fixtures compartidas: PDFs e imagenes generados al vuelo en una carpeta temporal.
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pymupdf
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
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


CERTIFICATE_PASSWORD = "clave-del-certificado"


def make_certificate(
    path: Path,
    *,
    name: str = "Firmante de Prueba",
    password: str | None = CERTIFICATE_PASSWORD,
    valid_days: tuple[int, int] = (-1, 365),
) -> tuple[Path, bytes]:
    """
    Crea un certificado autofirmado .p12 y devuelve ``(ruta, certificado DER)``.
    ``valid_days`` son los dias de inicio y fin de vigencia relativos a hoy.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([
        x509.NameAttribute(x509.NameOID.COMMON_NAME, name),
        x509.NameAttribute(x509.NameOID.COUNTRY_NAME, "CO"),
    ])
    now = datetime.now(UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now + timedelta(days=valid_days[0]))
        .not_valid_after(now + timedelta(days=valid_days[1]))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=True, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    encryption = (
        serialization.BestAvailableEncryption(password.encode()) if password else serialization.NoEncryption()
    )
    path.write_bytes(pkcs12.serialize_key_and_certificates(b"prueba", key, certificate, None, encryption))
    return path, certificate.public_bytes(serialization.Encoding.DER)


@pytest.fixture(scope="session")
def certificate(tmp_path_factory) -> tuple[Path, bytes]:
    """Certificado autofirmado vigente protegido con ``CERTIFICATE_PASSWORD``."""
    return make_certificate(tmp_path_factory.mktemp("cert") / "firmante.p12")
