"""
Utilidades de archivos compartidas por todas las operaciones.

La escritura de resultados es atomica: cada operacion escribe en un archivo
temporal junto al destino y solo lo reemplaza si termino sin errores. Asi un
fallo nunca deja un PDF corrupto ni destruye un archivo previo.
"""

import os
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

from .errors import InvalidInputError, OutputError

PDF_EXTENSIONS = (".pdf",)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")


def as_path(file_path: str | Path) -> Path:
    """Normaliza una ruta (expande ``~`` y la vuelve absoluta)."""
    if isinstance(file_path, str) and not file_path.strip():
        raise InvalidInputError("Debe indicar una ruta de archivo.")
    return Path(file_path).expanduser().resolve()


def require_file(file_path: str | Path, extensions: tuple[str, ...]) -> Path:
    """Valida que la ruta exista, sea un archivo y tenga una extension admitida."""
    path = as_path(file_path)
    if not path.exists():
        raise InvalidInputError(f"El archivo no existe: {path}")
    if not path.is_file():
        raise InvalidInputError(f"La ruta no es un archivo: {path}")
    if path.suffix.lower() not in extensions:
        expected = ", ".join(extensions)
        raise InvalidInputError(f"'{path.name}' no es valido. Formatos admitidos: {expected}")
    return path


def prepare_output(output_file: str | Path, *inputs: Path, extension: str = ".pdf") -> Path:
    """
    Normaliza la ruta de salida: fuerza la extension, crea la carpeta destino y
    verifica que no coincida con ninguno de los archivos de entrada.
    """
    output_path = as_path(output_file)
    if output_path.suffix.lower() != extension:
        output_path = output_path.with_name(output_path.name + extension)
    if output_path in inputs:
        raise InvalidInputError("El archivo de salida debe ser distinto a los archivos de origen.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def unique_path(path: Path) -> Path:
    """Devuelve ``path`` o, si ya existe, ``nombre (n).ext`` con el primer n libre."""
    if not path.exists():
        return path
    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def dedupe(paths: Iterable[str | Path]) -> list[Path]:
    """Normaliza rutas conservando el orden y descartando duplicados."""
    return list(dict.fromkeys(as_path(path) for path in paths))


@contextmanager
def atomic_output(output_path: Path) -> Iterator[Path]:
    """
    Entrega una ruta temporal en la misma carpeta que ``output_path``. Al salir
    sin excepciones el temporal reemplaza al destino; si hay error se elimina.
    """
    temp_path = output_path.with_name(f".{output_path.stem}.{uuid.uuid4().hex[:8]}.tmp{output_path.suffix}")
    try:
        yield temp_path
        if not temp_path.exists():
            raise OutputError(f"No se genero el archivo de salida: {output_path.name}")
        try:
            os.replace(temp_path, output_path)
        except PermissionError as error:
            raise OutputError(
                f"No se pudo guardar '{output_path.name}'. "
                "Verifique que no este abierto en otro programa."
            ) from error
    finally:
        temp_path.unlink(missing_ok=True)
