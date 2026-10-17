"""
Interfaz de linea de comandos.

Sin argumentos abre la interfaz grafica. Con un subcomando ejecuta la
operacion directamente usando el mismo nucleo que la GUI:

    python main.pyw merge a.pdf b.pdf -o unido.pdf
    python main.pyw extract informe.pdf -p "1-3,8" -o resumen.pdf
    python main.pyw lock contrato.pdf -o protegido.pdf
    python main.pyw sign contrato.pdf --image firma.png --page 2 --x 400 --y 700

Las contrasenas se piden de forma oculta si no se pasan como argumento.
"""

import argparse
import getpass
import logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from . import __app_name__, __version__, core, paths
from .logging_setup import configure_logging

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Define los subcomandos y sus argumentos."""
    parser = argparse.ArgumentParser(
        prog="pdfmanagement",
        description=f"{__app_name__} {__version__}: herramienta local para trabajar con PDFs.",
        epilog="Sin subcomando se abre la interfaz grafica.",
    )
    parser.add_argument("--version", action="version", version=f"{__app_name__} {__version__}")
    parser.add_argument("--debug", action="store_true", help="registro detallado en log/app.log")
    commands = parser.add_subparsers(dest="command", metavar="comando")

    commands.add_parser("gui", help="abre la interfaz grafica (por defecto)")

    merge = commands.add_parser("merge", help="une varios PDFs en uno")
    merge.add_argument("inputs", nargs="+", type=Path, help="PDFs en el orden deseado")
    merge.add_argument("-o", "--output", type=Path, required=True)
    merge.add_argument("--bookmarks", action="store_true", help="crea un marcador por archivo")

    extract = commands.add_parser("extract", help="extrae paginas a un PDF nuevo")
    extract.add_argument("input", type=Path)
    extract.add_argument("-p", "--pages", required=True, help='ej. "1-3,8", "5-", "all", "odd", "even"')
    extract.add_argument("-o", "--output", type=Path, required=True)
    extract.add_argument("--password", help="contrasena del PDF de origen")
    extract.add_argument("--output-password", help="protege el PDF generado")

    convert = commands.add_parser("convert", help="convierte Word/Excel a PDF (requiere Office)")
    convert.add_argument("input", type=Path)
    convert.add_argument("-o", "--output", type=Path)

    sign = commands.add_parser("sign", help="estampa una imagen de firma")
    sign.add_argument("input", type=Path)
    sign.add_argument("--image", type=Path, required=True)
    sign.add_argument("-o", "--output", type=Path)
    sign.add_argument("--page", type=int, help="pagina desde 1 (por defecto la ultima)")
    sign.add_argument("--x", type=float, default=72.0, help="borde izquierdo en puntos")
    sign.add_argument("--y", type=float, default=72.0, help="borde superior en puntos")
    sign.add_argument("--width", type=float, default=core.DEFAULT_SIGNATURE_WIDTH, help="ancho en puntos")
    sign.add_argument("--all-pages", action="store_true", help="firma todas las paginas")
    sign.add_argument("--password", help="contrasena del PDF de origen")

    for name, help_text in (("lock", "protege un PDF con contrasena"), ("unlock", "quita la contrasena")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("input", type=Path)
        command.add_argument("-o", "--output", type=Path)
        command.add_argument("--password")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada. Devuelve el codigo de salida del proceso."""
    args = build_parser().parse_args(argv)
    paths.ensure_data_dirs()
    configure_logging(debug=args.debug)

    if args.command in (None, "gui"):
        from .gui import run_gui

        run_gui()
        return 0

    try:
        result = _COMMANDS[args.command](args)
    except core.PdfManagementError as error:
        logger.debug("Fallo el comando %s", args.command, exc_info=True)
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(f"Archivo generado: {result}")
    return 0


def _default_output(source: Path, suffix: str) -> Path:
    return core.unique_path(source.with_name(f"{source.stem}_{suffix}.pdf"))


def _with_password_prompt(operation: Callable[[str | None], Path], password: str | None) -> Path:
    """Ejecuta ``operation`` y, si el PDF pide contrasena, la solicita en consola."""
    try:
        return operation(password)
    except core.PasswordRequiredError as error:
        if password is not None or not sys.stdin or not sys.stdin.isatty():
            raise
        return operation(getpass.getpass(f"Contrasena de '{error.file_path.name}': "))


def _merge(args: argparse.Namespace) -> Path:
    return core.merge_pdfs(args.inputs, args.output, add_bookmarks=args.bookmarks)


def _extract(args: argparse.Namespace) -> Path:
    return _with_password_prompt(
        lambda password: core.extract_pages(
            args.input, args.output, args.pages, password=password, output_password=args.output_password
        ),
        args.password,
    )


def _convert(args: argparse.Namespace) -> Path:
    output = args.output or core.unique_path(args.input.with_suffix(".pdf"))
    return core.convert_to_pdf(args.input, output)


def _sign(args: argparse.Namespace) -> Path:
    placement = core.SignaturePlacement(
        x=args.x, y=args.y, width=args.width, page_number=args.page, all_pages=args.all_pages
    )
    output = args.output or _default_output(args.input, "firmado")
    return _with_password_prompt(
        lambda password: core.sign_pdf_with_image(args.input, output, args.image, placement, password=password),
        args.password,
    )


def _lock(args: argparse.Namespace) -> Path:
    password = args.password
    if password is None:
        password = getpass.getpass("Nueva contrasena: ")
        if getpass.getpass("Confirme la contrasena: ") != password:
            raise core.InvalidInputError("Las contrasenas no coinciden.")
    return core.lock_pdf(args.input, args.output or _default_output(args.input, "protegido"), password)


def _unlock(args: argparse.Namespace) -> Path:
    password = args.password if args.password is not None else getpass.getpass("Contrasena actual: ")
    return core.unlock_pdf(args.input, args.output or _default_output(args.input, "sin_clave"), password)


_COMMANDS: dict[str, Callable[[argparse.Namespace], Path]] = {
    "merge": _merge,
    "extract": _extract,
    "convert": _convert,
    "sign": _sign,
    "lock": _lock,
    "unlock": _unlock,
}
