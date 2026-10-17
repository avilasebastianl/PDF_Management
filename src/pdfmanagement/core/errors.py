"""
Jerarquia de excepciones del nucleo.

Todas heredan de ``PdfManagementError`` para que la GUI y la CLI puedan
distinguir errores esperados (mostrados al usuario) de fallos inesperados.
"""

from pathlib import Path


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
        super().__init__(message or f"El PDF '{self.file_path.name}' esta protegido con contrasena.")


class WrongPasswordError(PasswordRequiredError):
    """La contrasena indicada no abre el PDF."""

    def __init__(self, file_path: Path) -> None:
        super().__init__(file_path, f"La contrasena de '{Path(file_path).name}' no es correcta.")


class ConversionError(PdfManagementError):
    """Fallo la conversion de un documento de Office a PDF."""
