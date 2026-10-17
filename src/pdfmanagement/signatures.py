"""
Biblioteca de firmas del usuario (imagenes guardadas en ``signs/``).
"""

import shutil
from datetime import datetime
from pathlib import Path

from . import paths
from .core.files import IMAGE_EXTENSIONS, require_file


def list_signatures() -> list[Path]:
    """Firmas guardadas, de la mas reciente a la mas antigua."""
    paths.SIGNATURES_DIR.mkdir(parents=True, exist_ok=True)
    signatures = [
        file for file in paths.SIGNATURES_DIR.iterdir()
        if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS
    ]
    return sorted(signatures, key=lambda file: file.stat().st_mtime, reverse=True)


def clean_name(name: str) -> str:
    """Nombre de archivo seguro: solo letras, numeros, guion y guion bajo."""
    cleaned = "".join(char for char in name.strip() if char.isalnum() or char in "_- ").strip().replace(" ", "_")
    return cleaned or f"firma_{datetime.now():%Y%m%d_%H%M%S}"


def signature_path_for(name: str, extension: str) -> Path:
    """Ruta libre dentro de ``signs/`` para una firma nueva."""
    paths.SIGNATURES_DIR.mkdir(parents=True, exist_ok=True)
    base = paths.SIGNATURES_DIR / f"{clean_name(name)}{extension.lower()}"
    candidate, counter = base, 2
    while candidate.exists():
        candidate = base.with_name(f"{base.stem}_{counter}{base.suffix}")
        counter += 1
    return candidate


def import_signature(source: str | Path, name: str | None = None) -> Path:
    """Copia una imagen a la biblioteca de firmas y devuelve su nueva ruta."""
    source_path = require_file(source, IMAGE_EXTENSIONS)
    if source_path.parent == paths.SIGNATURES_DIR.resolve():
        return source_path
    target = signature_path_for(name or source_path.stem, source_path.suffix)
    shutil.copy2(source_path, target)
    return target


def delete_signature(signature: Path) -> None:
    """Elimina una firma de la biblioteca (solo archivos dentro de ``signs/``)."""
    signature = signature.resolve()
    if signature.parent != paths.SIGNATURES_DIR.resolve():
        raise ValueError("Solo se pueden borrar firmas de la biblioteca.")
    signature.unlink(missing_ok=True)
