"""
Firma digital con certificado (PAdES B-B) a partir de un archivo .pfx/.p12.

A diferencia de la firma visual, incrusta una firma criptografica CMS que
prueba la autoria y la integridad: cualquier cambio posterior al documento la
invalida. Todo ocurre sin conexion a internet (no se consulta ninguna TSA ni
OCSP) y la contrasena del certificado solo vive en memoria durante la firma.

La apariencia visible reutiliza ``signature_rect``: el recuadro que se ve en
el visor es el mismo que queda en el PDF. Se compone de la imagen de firma
(opcional) y, debajo, una leyenda con el titular y la fecha.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pymupdf
from asn1crypto import pkcs12 as asn1_pkcs12
from cryptography import x509
from cryptography.hazmat.primitives.serialization import pkcs12
from PIL import Image
from pyhanko.pdf_utils import generic
from pyhanko.pdf_utils.crypt.api import AuthStatus
from pyhanko.pdf_utils.images import PdfImage
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.layout import AxisAlignment, BoxConstraints, InnerScaling, Margins, SimpleBoxLayoutRule
from pyhanko.pdf_utils.misc import PdfError
from pyhanko.pdf_utils.text import TextBoxStyle
from pyhanko.sign import fields, signers
from pyhanko.sign.general import SigningError
from pyhanko.stamp import TextStamp, TextStampStyle

from .documents import open_document
from .errors import (
    CertificateError,
    DigitalSignatureError,
    InvalidInputError,
    PasswordRequiredError,
    WrongCertificatePasswordError,
    WrongPasswordError,
)
from .files import PDF_EXTENSIONS, atomic_output, prepare_output, require_file
from .signing import SignaturePlacement, image_aspect_ratio, load_signature, resolve_page_index, signature_rect

logger = logging.getLogger(__name__)

CERTIFICATE_EXTENSIONS = (".pfx", ".p12")

CAPTION_RATIO = 0.24
"""Alto de la leyenda ("Firmado digitalmente por...") relativo al ancho del recuadro."""

CAPTION_TEXT = "Firmado digitalmente por:\n%(signer)s\nFecha: %(ts)s"
TIMESTAMP_FORMAT = "%d/%m/%Y %H:%M:%S %z"
FIELD_PREFIX = "FirmaDigital"


@dataclass(frozen=True)
class CertificateInfo:
    """Datos del certificado que se muestran al usuario antes de firmar."""

    path: Path
    subject: str
    issuer: str
    valid_from: datetime
    valid_until: datetime
    self_signed: bool


def digital_aspect_ratio(image_aspect: float | None) -> float:
    """
    Relacion alto/ancho del recuadro de la firma digital: la imagen (si hay)
    conserva el mismo tamano que en la firma visual y la leyenda va debajo.
    """
    return (image_aspect or 0.0) + CAPTION_RATIO


# * Certificado ----------------------------------------------------------------

def _common_name(name: x509.Name) -> str:
    attributes = name.get_attributes_for_oid(x509.NameOID.COMMON_NAME)
    return str(attributes[0].value) if attributes else name.rfc4514_string()


def _load_pkcs12(pfx_path: Path, password: str | None) -> tuple[bytes, bytes | None, x509.Certificate]:
    """Abre el .pfx y devuelve ``(datos, contrasena usada, certificado)`` o lanza un error claro."""
    try:
        data = pfx_path.read_bytes()
    except OSError as error:
        raise InvalidInputError(f"No se pudo leer el certificado '{pfx_path.name}': {error}") from error
    try:
        asn1_pkcs12.Pfx.load(data, strict=True)["auth_safe"]["content_type"].native
    except (ValueError, TypeError, KeyError) as error:
        raise CertificateError(f"'{pfx_path.name}' no es un certificado .pfx/.p12 valido.") from error

    # Sin contrasena se prueba tanto "sin cifrar" como "contrasena vacia".
    candidates = [password.encode("utf-8")] if password else [None, b""]
    for secret in candidates:
        try:
            key, certificate, _ = pkcs12.load_key_and_certificates(data, secret)
        except ValueError:
            continue
        if key is None or certificate is None:
            raise CertificateError(f"El certificado '{pfx_path.name}' no contiene la clave privada necesaria para firmar.")
        return data, secret, certificate
    raise WrongCertificatePasswordError(pfx_path)


def _check_validity(pfx_path: Path, certificate: x509.Certificate) -> None:
    now = datetime.now(UTC)
    if certificate.not_valid_after_utc < now:
        expired = certificate.not_valid_after_utc.astimezone().strftime("%d/%m/%Y")
        raise CertificateError(f"El certificado '{pfx_path.name}' vencio el {expired}.")
    if certificate.not_valid_before_utc > now:
        start = certificate.not_valid_before_utc.astimezone().strftime("%d/%m/%Y")
        raise CertificateError(f"El certificado '{pfx_path.name}' aun no es valido (desde el {start}).")


def load_certificate(pfx_file: str | Path, pfx_password: str | None) -> CertificateInfo:
    """
    Verifica que el certificado abra con la contrasena, tenga clave privada y
    este vigente. Permite validar la contrasena antes de iniciar la firma.

    Raises:
        WrongCertificatePasswordError: la contrasena no abre el certificado.
        CertificateError: archivo danado, sin clave privada, vencido o aun no vigente.
    """
    pfx_path = require_file(pfx_file, CERTIFICATE_EXTENSIONS)
    _, _, certificate = _load_pkcs12(pfx_path, pfx_password)
    _check_validity(pfx_path, certificate)
    return CertificateInfo(
        path=pfx_path,
        subject=_common_name(certificate.subject),
        issuer=_common_name(certificate.issuer),
        valid_from=certificate.not_valid_before_utc,
        valid_until=certificate.not_valid_after_utc,
        self_signed=certificate.subject == certificate.issuer,
    )


def _create_signer(pfx_path: Path, pfx_password: str | None) -> tuple[signers.SimpleSigner, str]:
    data, secret, certificate = _load_pkcs12(pfx_path, pfx_password)
    _check_validity(pfx_path, certificate)
    try:
        signer = signers.SimpleSigner.load_pkcs12_data(data, other_certs=(), passphrase=secret)
    except ValueError as error:
        raise CertificateError(f"No se pudo usar el certificado '{pfx_path.name}': {error}") from error
    return signer, _common_name(certificate.subject)


# * Apariencia -----------------------------------------------------------------

# Matrices que giran la apariencia en sentido contrario a ``/Rotate`` para que
# la firma se vea derecha en paginas rotadas. ``w`` y ``h`` son el ancho y el
# alto del recuadro tal como se ve en pantalla.
_COUNTER_ROTATION = {
    90: lambda w, h: (0, 1, -1, 0, h, 0),
    180: lambda w, h: (-1, 0, 0, -1, w, h),
    270: lambda w, h: (0, -1, 1, 0, 0, w),
}


class _OrientedTextStamp(TextStamp):
    def as_form_xobject(self):
        xobject = super().as_form_xobject()
        rotation = self.style.page_rotation
        if rotation in _COUNTER_ROTATION:
            matrix = _COUNTER_ROTATION[rotation](self.box.width, self.box.height)
            xobject["/Matrix"] = generic.ArrayObject(generic.FloatObject(value) for value in matrix)
        return xobject


@dataclass(frozen=True)
class _OrientedTextStampStyle(TextStampStyle):
    """Estampa de texto (con imagen de fondo) que compensa la rotacion de la pagina."""

    page_rotation: int = 0

    def create_stamp(self, writer, box, text_params):
        if self.page_rotation in (90, 270):
            box = BoxConstraints(width=box.height, height=box.width)
        return _OrientedTextStamp(writer=writer, style=self, box=box, text_params=text_params)


def _stamp_style(image: Image.Image | None, rect: pymupdf.Rect, rotation: int) -> _OrientedTextStampStyle:
    caption_height = rect.width * CAPTION_RATIO
    image_height = rect.height - caption_height
    padding = caption_height * 0.08
    # Se alinea al minimo (izquierda/abajo): con ALIGN_MID pyHanko advierte por
    # redondeo cuando el contenido ocupa exactamente el espacio disponible.
    return _OrientedTextStampStyle(
        page_rotation=rotation,
        stamp_text=CAPTION_TEXT,
        timestamp_format=TIMESTAMP_FORMAT,
        border_width=0,
        text_box_style=TextBoxStyle(font_size=10, text_color=(0.15, 0.15, 0.2)),
        inner_content_layout=SimpleBoxLayoutRule(
            x_align=AxisAlignment.ALIGN_MIN,
            y_align=AxisAlignment.ALIGN_MIN,
            margins=Margins(left=padding, right=padding, top=image_height + padding, bottom=padding),
            inner_content_scaling=InnerScaling.STRETCH_TO_FIT,
        ),
        background=PdfImage(image) if image is not None else None,
        background_opacity=1.0,
        background_layout=SimpleBoxLayoutRule(
            x_align=AxisAlignment.ALIGN_MIN,
            y_align=AxisAlignment.ALIGN_MAX,
            margins=Margins(bottom=caption_height),
        ),
    )


def _field_box(page: pymupdf.Page, visible_rect: pymupdf.Rect) -> tuple[float, float, float, float]:
    """Convierte el recuadro visible (origen arriba a la izquierda) a coordenadas PDF."""
    box = visible_rect * page.derotation_matrix * ~page.transformation_matrix
    box.normalize()
    return box.x0, box.y0, box.x1, box.y1


def _unique_field_name(writer: IncrementalPdfFileWriter) -> str:
    existing = {name for name, _, _ in fields.enumerate_sig_fields(writer.prev)}
    counter = 1
    while f"{FIELD_PREFIX}{counter}" in existing:
        counter += 1
    return f"{FIELD_PREFIX}{counter}"


# * Firma ----------------------------------------------------------------------

def sign_pdf_with_certificate(
    input_file: str | Path,
    output_file: str | Path,
    pfx_path: str | Path,
    pfx_password: str | None,
    *,
    placement: SignaturePlacement | None = None,
    signature_image: str | Path | None = None,
    reason: str | None = None,
    location: str | None = None,
    password: str | None = None,
) -> Path:
    """
    Firma el PDF con el certificado (PAdES B-B, SHA-256) mediante una
    actualizacion incremental, por lo que las firmas previas siguen validas.

    Args:
        placement: Posicion de la firma visible; ``None`` crea una firma invisible.
        signature_image: Imagen opcional que acompana la leyenda de la firma visible.
        reason / location: Motivo y lugar que se guardan en la firma.
        password: Contrasena del PDF de origen, si esta protegido.

    Returns:
        Ruta del PDF firmado.
    """
    source = require_file(input_file, PDF_EXTENSIONS)
    certificate = require_file(pfx_path, CERTIFICATE_EXTENSIONS)
    output_path = prepare_output(output_file, source)
    if placement is not None and placement.all_pages:
        raise InvalidInputError("La firma digital se ubica en una sola pagina. Desmarque 'todas las paginas'.")
    signer, signer_name = _create_signer(certificate, pfx_password)

    field_spec = None
    stamp_style = None
    if placement is not None:
        image = load_signature(signature_image) if signature_image else None
        aspect_ratio = digital_aspect_ratio(image_aspect_ratio(image) if image else None)
        with open_document(source, password) as document:
            page_index = resolve_page_index(placement.page_number, document.page_count)
            page = document[page_index]
            visible_rect = signature_rect(page.rect, placement, aspect_ratio)
            box = _field_box(page, visible_rect)
            rotation = page.rotation
        stamp_style = _stamp_style(image, visible_rect, rotation)

    try:
        with open(source, "rb") as stream, atomic_output(output_path) as temp_path:
            writer = IncrementalPdfFileWriter(stream, strict=False)
            if writer.prev.encrypted:
                result = writer.encrypt(password or "")
                if result.status == AuthStatus.FAILED:
                    if not password:
                        raise PasswordRequiredError(source)
                    raise WrongPasswordError(source)
            field_name = _unique_field_name(writer)
            if placement is not None:
                field_spec = fields.SigFieldSpec(sig_field_name=field_name, on_page=page_index, box=box)
            metadata = signers.PdfSignatureMetadata(
                field_name=field_name,
                reason=reason or None,
                location=location or None,
                md_algorithm="sha256",
                subfilter=fields.SigSeedSubFilter.PADES,
            )
            pdf_signer = signers.PdfSigner(
                metadata,
                signer=signer,
                stamp_style=stamp_style,
                new_field_spec=field_spec,
            )
            with open(temp_path, "wb") as output:
                pdf_signer.sign_pdf(writer, output=output, appearance_text_params={"signer": signer_name})
    except (PdfError, SigningError) as error:
        raise DigitalSignatureError(f"No se pudo firmar '{source.name}': {error}") from error

    logger.info("PDF firmado digitalmente por %s: %s", signer_name, output_path)
    return output_path
