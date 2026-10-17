"""
Interprete de selecciones de paginas escritas por el usuario.
"""

from .errors import InvalidInputError

_ALL = {"all", "todo", "todos", "todas"}
_ODD = {"odd", "impar", "impares"}
_EVEN = {"even", "par", "pares"}


def parse_page_selection(selection: str, total_pages: int) -> list[int]:
    """
    Convierte una seleccion legible (paginas desde 1) en indices base cero.

    Formatos admitidos, combinables con comas o punto y coma:

    - ``5``         una pagina.
    - ``2-6``       un rango cerrado.
    - ``8-``        desde la pagina 8 hasta la ultima.
    - ``-3``        desde la primera hasta la pagina 3.
    - ``all`` / ``todo``, ``odd`` / ``impar``, ``even`` / ``par``.

    El orden se respeta y los duplicados se eliminan conservando la primera
    aparicion: ``3,1-2`` produce ``[2, 0, 1]``.

    Raises:
        InvalidInputError: si la seleccion esta vacia, mal escrita o fuera de rango.
    """
    normalized = selection.strip().lower().replace(" ", "").replace(";", ",")
    if not normalized:
        raise InvalidInputError("Debe indicar las paginas a extraer.")
    if total_pages < 1:
        raise InvalidInputError("El PDF no tiene paginas.")

    if normalized in _ALL:
        return list(range(total_pages))
    if normalized in _ODD:
        return list(range(0, total_pages, 2))
    if normalized in _EVEN:
        return list(range(1, total_pages, 2))

    indexes: list[int] = []
    for block in filter(None, normalized.split(",")):
        if "-" in block:
            start_text, end_text = block.split("-", maxsplit=1)
            start = _to_page(start_text, block) if start_text else 1
            end = _to_page(end_text, block) if end_text else total_pages
            if start > end:
                raise InvalidInputError(f"El rango '{block}' esta invertido.")
            indexes.extend(range(start - 1, end))
        else:
            indexes.append(_to_page(block, block) - 1)

    unique_indexes = list(dict.fromkeys(indexes))
    out_of_range = [index + 1 for index in unique_indexes if index >= total_pages]
    if out_of_range:
        raise InvalidInputError(f"Paginas fuera de rango: {out_of_range}. El PDF tiene {total_pages} paginas.")
    if not unique_indexes:
        raise InvalidInputError("No se encontraron paginas validas.")
    return unique_indexes


def _to_page(text: str, block: str) -> int:
    if not text.isdigit() or int(text) < 1:
        raise InvalidInputError(f"Seleccion de paginas invalida: '{block}'")
    return int(text)
