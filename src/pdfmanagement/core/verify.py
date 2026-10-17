"""
Verificacion de firmas digitales existentes (pyHanko).

Para cada firma informa quien firmo, cuando, si los bytes firmados siguen
intactos, si la firma es criptograficamente valida, si el certificado es de
confianza y si el documento se modifico despues de firmar. Todo local: no se
consultan servidores (OCSP/CRL), por eso un certificado sin raiz de confianza
en el equipo aparece como "no verificada la identidad".
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign.diff_analysis import ModificationLevel
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko.sign.validation.errors import SignatureValidationError
from pyhanko_certvalidator import ValidationContext

from ..i18n import tr
from .errors import InvalidInputError, PasswordRequiredError, WrongPasswordError
from .files import PDF_EXTENSIONS, require_file

VALID, UNTRUSTED, MODIFIED, BROKEN = "valida", "identidad_no_verificada", "modificada", "invalida"


@dataclass(frozen=True)
class SignatureReport:
    field: str
    signer: str
    signed_at: datetime | None
    intact: bool  # los bytes firmados no cambiaron
    valid: bool  # la firma criptografica es correcta
    trusted: bool  # el certificado encadena con una raiz de confianza del equipo
    modified_after: bool  # hubo cambios no permitidos despues de firmar
    error: str = ""

    @property
    def state(self) -> str:
        if self.error or not self.intact or not self.valid:
            return BROKEN
        if self.modified_after:
            return MODIFIED
        return VALID if self.trusted else UNTRUSTED

    @property
    def summary(self) -> str:
        return {
            VALID: tr("Firma válida: el documento no cambió desde que se firmó."),
            UNTRUSTED: tr(
                "Firma correcta y documento sin cambios, pero la identidad del firmante no se pudo "
                "verificar (certificado autofirmado o sin entidad de confianza en este equipo)."
            ),
            MODIFIED: tr("La firma es correcta, pero el documento se modificó después de firmarse."),
            BROKEN: tr("Firma no válida: el contenido firmado cambió o la firma está dañada."),
        }[self.state]


def verify_signatures(pdf_file: str | Path, password: str | None = None) -> list[SignatureReport]:
    """Verifica todas las firmas digitales del PDF (lista vacia si no tiene)."""
    path = require_file(pdf_file, PDF_EXTENSIONS)
    try:
        with path.open("rb") as stream:
            reader = PdfFileReader(stream, strict=False)
            if reader.encrypted:
                if not password:
                    raise PasswordRequiredError(path)
                result = reader.decrypt(password)
                if getattr(result, "status", None) is not None and "FAILED" in str(result.status):
                    raise WrongPasswordError(path)
            context = ValidationContext(allow_fetching=False)
            return [_report(signature, context) for signature in reader.embedded_signatures]
    except (PasswordRequiredError, WrongPasswordError):
        raise
    except (OSError, ValueError) as error:
        raise InvalidInputError(
            tr("No se pudieron leer las firmas de '{name}': {error}", name=path.name, error=error)
        ) from error


def _report(signature, context: ValidationContext) -> SignatureReport:
    field = signature.field_name or "?"
    try:
        status = validate_pdf_signature(signature, context)
    except (SignatureValidationError, ValueError, KeyError) as error:
        return SignatureReport(field, "?", None, False, False, False, False, error=str(error))
    level = status.modification_level
    modified = (level is not None and level > ModificationLevel.LTA_UPDATES) or status.docmdp_ok is False
    try:
        signer = status.signing_cert.subject.human_friendly
    except AttributeError:
        signer = "?"
    return SignatureReport(
        field=field,
        signer=signer,
        signed_at=status.signer_reported_dt,
        intact=bool(status.intact),
        valid=bool(status.valid),
        trusted=bool(status.trusted),
        modified_after=modified,
    )
