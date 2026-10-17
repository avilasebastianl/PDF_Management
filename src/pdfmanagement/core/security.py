"""
Proteccion (cifrado) y desproteccion de PDFs.

La aplicacion nunca intenta adivinar contrasenas: para desbloquear un PDF el
usuario debe conocer su contrasena.
"""

import logging
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from .errors import InvalidInputError, WrongPasswordError
from .files import PDF_EXTENSIONS, atomic_output, prepare_output, require_file

logger = logging.getLogger(__name__)

ENCRYPTION_ALGORITHM = "AES-256"
MIN_PASSWORD_LENGTH = 4


def lock_pdf(
    input_file: str | Path,
    output_file: str | Path,
    password: str,
    *,
    owner_password: str | None = None,
) -> Path:
    """
    Genera una copia del PDF protegida con contrasena (AES-256).

    Conserva marcadores, formularios y metadatos del original.

    Args:
        password: Contrasena para abrir el documento.
        owner_password: Contrasena de propietario; por defecto la misma.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise InvalidInputError(f"La contrasena debe tener al menos {MIN_PASSWORD_LENGTH} caracteres.")

    source = require_file(input_file, PDF_EXTENSIONS)
    output_path = prepare_output(output_file, source)
    if PdfReader(source).is_encrypted:
        raise InvalidInputError("El PDF ya esta protegido. Desbloqueelo antes de volver a protegerlo.")

    writer = PdfWriter(clone_from=source)
    try:
        writer.encrypt(password, owner_password or password, algorithm=ENCRYPTION_ALGORITHM)
        with atomic_output(output_path) as temp_path:
            writer.write(temp_path)
    finally:
        writer.close()

    logger.info("PDF protegido: %s", output_path)
    return output_path


def unlock_pdf(input_file: str | Path, output_file: str | Path, password: str) -> Path:
    """
    Genera una copia sin proteccion de un PDF cuya contrasena se conoce.

    Raises:
        InvalidInputError: el PDF no esta protegido.
        WrongPasswordError: la contrasena no es correcta.
    """
    source = require_file(input_file, PDF_EXTENSIONS)
    output_path = prepare_output(output_file, source)
    reader = PdfReader(source)
    if not reader.is_encrypted:
        raise InvalidInputError("El PDF no esta protegido.")
    if not password or not reader.decrypt(password):
        raise WrongPasswordError(source)

    writer = PdfWriter(clone_from=reader)
    try:
        with atomic_output(output_path) as temp_path:
            writer.write(temp_path)
    finally:
        writer.close()

    logger.info("PDF desprotegido: %s", output_path)
    return output_path
