# Codigo de terceros (`_vendor`)

Paquetes externos incluidos directamente en el proyecto. Se mantienen **sin
modificar**: los ajustes de la aplicacion se hacen en un envoltorio propio, de
modo que actualizar un paquete consiste en reemplazar sus archivos.

| Paquete | Origen | Licencia | Uso en la aplicacion |
|---|---|---|---|
| `ctk_scrollable_dropdown` | [Akascape/CTkScrollableDropdown](https://github.com/Akascape/CTkScrollableDropdown) (`ctk_scrollable_dropdown.py`, copia del 15/03/2026) | MIT (ver `ctk_scrollable_dropdown/LICENSE`) | Listas desplegables con desplazamiento; se usa a traves de `gui/dropdown.py` |

## Convenciones

- Carpeta `_vendor` (con guion bajo): codigo interno que no forma parte de la
  API propia del proyecto, igual que hacen `pip` o `setuptools`.
- Un subpaquete por dependencia, con nombre en minusculas (PEP 8) y su archivo
  `LICENSE`.
- Nunca se importa directamente desde las paginas: se usa el envoltorio, que
  aplica el estilo de la aplicacion y corrige comportamientos.

## Como actualizar `ctk_scrollable_dropdown`

1. Descargue `ctk_scrollable_dropdown.py` desde el repositorio original.
2. Reemplace el archivo en `_vendor/ctk_scrollable_dropdown/` y actualice la fecha de la tabla.
3. Ejecute `python -m pytest` (incluye pruebas de los desplegables).
