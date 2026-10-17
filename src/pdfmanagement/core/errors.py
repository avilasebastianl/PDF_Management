"""
Jerarquia de excepciones del nucleo.

Todas heredan de ``PdfManagementError`` para que la GUI y la CLI puedan
distinguir errores esperados (mostrados al usuario) de fallos inesperados.
"""

from pathlib import Path

from ..i18n import tr


class PdfManagementError(Exception):
    """Error base de la aplicacion. Su mensaje es apto para el usuario final."""


class InvalidInputError(PdfManagementError):
    """Entrada invalida: ruta inexistente, extension incorrecta, seleccion mal escrita..."""


class OutputError(PdfManagementError):
    """No fue posible escribir el archivo de salida."""


class PasswordRequiredError(PdfManagementError):
    """El PDF esta protegido y no se indico contrasena."""

    def __init__(self, file_path: Path, message: str | None = None) -> None:
        self.file_path = Path(file_path)
        super().__init__(message or tr("El PDF '{name}' está protegido con contraseña.", name=self.file_path.name))


class WrongPasswordError(PasswordRequiredError):
    """La contrasena indicada no abre el PDF."""

    def __init__(self, file_path: Path) -> None:
        super().__init__(file_path, tr("La contraseña de '{name}' no es correcta.", name=Path(file_path).name))


class ConversionError(PdfManagementError):
    """Fallo la conversion de un documento de Office a PDF."""


class DigitalSignatureError(PdfManagementError):
    """Fallo la firma digital con certificado."""


class CertificateError(DigitalSignatureError):
    """El certificado no es valido, esta vencido o no contiene la clave privada."""


class WrongCertificatePasswordError(CertificateError):
    """La contrasena indicada no abre el certificado .pfx/.p12."""

    def __init__(self, certificate_path: Path) -> None:
        self.certificate_path = Path(certificate_path)
        super().__init__(tr("La contraseña del certificado '{name}' no es correcta.", name=self.certificate_path.name))
