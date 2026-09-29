"""
Modulo principal de clases, funciones y metodos.
"""

import configparser
import json
import logging
import logging.config
import os
import sys
from pathlib import Path
from typing import Iterable

import comtypes
import comtypes.client
import pymupdf as fitz
import yaml
from pypdf import PdfReader, PdfWriter

from paths import *

# * Configuracion de logger
with open(os.path.join(path_to_config, "logger.yml"), encoding="utf-8") as f:
    logging.config.dictConfig(yaml.safe_load(f))

logger_user = logging.getLogger("user")
logger_dev = logging.getLogger("dev")


class TheManipulation:
    """
    Funciones para manipular archivos PDF y transformar documentos a PDF.
    """

    @staticmethod
    def _as_path(file_path: str | Path) -> Path:
        return Path(file_path).expanduser().resolve()

    @staticmethod
    def _validate_existing_file(file_path: str | Path, extensions: tuple[str, ...]) -> Path:
        path = TheManipulation._as_path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"El archivo no existe: {path}")
        if not path.is_file():
            raise ValueError(f"La ruta no es un archivo: {path}")
        if path.suffix.lower() not in extensions:
            raise ValueError(f"Extension invalida para '{path.name}'. Se esperaba: {extensions}")
        return path

    @staticmethod
    def _ensure_output_path(output_file: str | Path, extension: str = ".pdf") -> Path:
        output_path = TheManipulation._as_path(output_file)
        if output_path.suffix.lower() != extension:
            output_path = output_path.with_suffix(extension)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path

    @staticmethod
    def _validate_different_output(input_path: Path, output_path: Path) -> None:
        if input_path == output_path:
            raise ValueError("El archivo de salida debe ser distinto al archivo de origen.")

    @staticmethod
    def _valid_pdf_files(pdf_files: Iterable[str | Path]) -> list[Path]:
        valid_pdfs: list[Path] = []
        invalid_files: list[str] = []

        for pdf_file in pdf_files:
            try:
                valid_pdfs.append(TheManipulation._validate_existing_file(pdf_file, (".pdf",)))
            except (FileNotFoundError, ValueError) as error:
                invalid_files.append(str(pdf_file))
                logger_dev.warning(error)

        if invalid_files:
            logger_user.warning(f"Archivos ignorados: {invalid_files}")
        if not valid_pdfs:
            raise ValueError("No hay archivos PDF validos para procesar.")

        return valid_pdfs

    @staticmethod
    def concatenate_pdf_files(pdf_files: Iterable[str | Path], pdf_output: str | Path) -> Path:
        """
        Concatena uno o mas archivos PDF en un unico archivo de salida.

        Args:
            pdf_files: Lista o iterable con las rutas de los PDF a unir.
            pdf_output: Ruta del archivo PDF final.

        Returns:
            Path: Ruta del PDF generado.
        """
        valid_pdfs = TheManipulation._valid_pdf_files(pdf_files)
        output_path = TheManipulation._ensure_output_path(pdf_output)
        if output_path in valid_pdfs:
            raise ValueError("El archivo de salida no puede ser uno de los PDFs de origen.")

        writer = PdfWriter()
        try:
            for pdf_file in valid_pdfs:
                writer.append(str(pdf_file))
            with output_path.open("wb") as output:
                writer.write(output)
        finally:
            writer.close()

        logger_user.info(f"PDF concatenado guardado en: {output_path}")
        return output_path

    @staticmethod
    def join_pdf_files(pdf_files: list[str], pdf_output: str) -> Path:
        """
        Alias compatible con el nombre anterior de la funcion.
        """
        return TheManipulation.concatenate_pdf_files(pdf_files, pdf_output)

    @staticmethod
    def _parse_page_selection(page_selection: str, total_pages: int) -> list[int]:
        """
        Convierte una seleccion flexible de paginas a indices base cero.
        """
        if not page_selection.strip():
            raise ValueError("Debe indicar al menos una pagina.")

        normalized_selection = page_selection.strip().lower().replace(" ", "")
        if normalized_selection in ("all", "todo", "todos"):
            return list(range(total_pages))
        if normalized_selection in ("odd", "impar", "impares"):
            return [index for index in range(total_pages) if (index + 1) % 2 != 0]
        if normalized_selection in ("even", "par", "pares"):
            return [index for index in range(total_pages) if (index + 1) % 2 == 0]

        page_indexes: list[int] = []
        for block in normalized_selection.split(","):
            if not block:
                continue

            if "-" in block:
                start_text, end_text = block.split("-", maxsplit=1)
                if not start_text.isdigit() or not end_text.isdigit():
                    raise ValueError(f"Rango de paginas invalido: {block}")

                start_page = int(start_text)
                end_page = int(end_text)
                if start_page > end_page:
                    raise ValueError(f"El rango '{block}' esta invertido.")

                page_indexes.extend(range(start_page - 1, end_page))
                continue

            if not block.isdigit():
                raise ValueError(f"Pagina invalida: {block}")
            page_indexes.append(int(block) - 1)

        unique_page_indexes = list(dict.fromkeys(page_indexes))
        invalid_pages = [
            page_index + 1
            for page_index in unique_page_indexes
            if page_index < 0 or page_index >= total_pages
        ]
        if invalid_pages:
            raise ValueError(
                f"Paginas fuera de rango: {invalid_pages}. El PDF tiene {total_pages} paginas."
            )

        if not unique_page_indexes:
            raise ValueError("No se encontraron paginas validas para extraer.")

        return unique_page_indexes

    @staticmethod
    def extract_pdf_pages(
        input_pdf: str | Path,
        output_pdf: str | Path,
        page_selection: str,
        password: str | None = None,
        output_password: str | None = None,
    ) -> Path:
        """
        Extrae paginas especificas de un PDF y las guarda en un nuevo archivo.

        Args:
            input_pdf: Ruta del PDF original.
            output_pdf: Ruta donde se guardara el nuevo PDF.
            page_selection: Paginas a extraer. Acepta valores como ``2,4,7,9``,
                rangos como ``2-5`` y combinaciones como ``1,3-6,10``. Tambien
                acepta ``all``, ``odd`` o ``even``.
            password: Contrasena del PDF, si esta protegido.
            output_password: Contrasena opcional para proteger el PDF generado.

        Returns:
            Path: Ruta del PDF generado.
        """
        input_path = TheManipulation._validate_existing_file(input_pdf, (".pdf",))
        output_path = TheManipulation._ensure_output_path(output_pdf)
        TheManipulation._validate_different_output(input_path, output_path)
        reader = PdfReader(str(input_path))

        if reader.is_encrypted:
            if not password or reader.decrypt(password) == 0:
                raise ValueError("El PDF esta protegido o la contrasena no es correcta.")

        page_indexes = TheManipulation._parse_page_selection(
            page_selection=page_selection,
            total_pages=len(reader.pages),
        )
        writer = PdfWriter()
        for page_index in page_indexes:
            writer.add_page(reader.pages[page_index])

        if output_password:
            writer.encrypt(output_password, output_password)

        with output_path.open("wb") as output:
            writer.write(output)

        logger_user.info(f"PDF desunido guardado en: {output_path}")
        return output_path

    @staticmethod
    def lock_pdf(input_pdf: str | Path, output_pdf: str | Path, password: str) -> Path:
        """
        Bloquea/encripta un PDF con una contrasena.

        Args:
            input_pdf: Ruta del PDF original.
            output_pdf: Ruta donde se guardara el PDF protegido.
            password: Contrasena que debera usar el usuario para abrir el PDF.

        Returns:
            Path: Ruta del PDF protegido.
        """
        if not password:
            raise ValueError("La contrasena no puede estar vacia.")

        input_path = TheManipulation._validate_existing_file(input_pdf, (".pdf",))
        output_path = TheManipulation._ensure_output_path(output_pdf)
        TheManipulation._validate_different_output(input_path, output_path)
        reader = PdfReader(str(input_path))
        writer = PdfWriter()

        if reader.is_encrypted:
            raise ValueError("El PDF ya esta bloqueado. Desbloquealo antes de volver a protegerlo.")

        for page in reader.pages:
            writer.add_page(page)

        writer.encrypt(password, password)
        with output_path.open("wb") as output:
            writer.write(output)

        logger_user.info(f"PDF bloqueado guardado en: {output_path}")
        return output_path

    @staticmethod
    def unlock_pdf(input_pdf: str | Path, output_pdf: str | Path, password: str) -> Path:
        """
        Desbloquea/desencripta un PDF usando su contrasena.

        Args:
            input_pdf: Ruta del PDF protegido.
            output_pdf: Ruta donde se guardara el PDF sin proteccion.
            password: Contrasena actual del PDF.

        Returns:
            Path: Ruta del PDF desbloqueado.
        """
        if not password:
            raise ValueError("Debe indicar la contrasena del PDF.")

        input_path = TheManipulation._validate_existing_file(input_pdf, (".pdf",))
        output_path = TheManipulation._ensure_output_path(output_pdf)
        TheManipulation._validate_different_output(input_path, output_path)
        reader = PdfReader(str(input_path))

        if reader.is_encrypted and reader.decrypt(password) == 0:
            raise ValueError("La contrasena no es correcta.")

        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        with output_path.open("wb") as output:
            writer.write(output)

        logger_user.info(f"PDF desbloqueado guardado en: {output_path}")
        return output_path

    @staticmethod
    def sign_pdf_with_text(
        input_pdf: str | Path,
        output_pdf: str | Path,
        signature_text: str,
        page_number: int = -1,
        x: float = 72,
        y: float = 72,
        width: float = 220,
        height: float = 55,
        font_size: int = 12,
    ) -> Path:
        """
        Agrega una firma visual en texto a un PDF.

        Nota: esto no es una firma digital criptografica con certificado.
        """
        if not signature_text:
            raise ValueError("El texto de firma no puede estar vacio.")

        input_path = TheManipulation._validate_existing_file(input_pdf, (".pdf",))
        output_path = TheManipulation._ensure_output_path(output_pdf)
        TheManipulation._validate_different_output(input_path, output_path)

        with fitz.open(input_path) as document:
            page = document[page_number]
            box = fitz.Rect(x, y, x + width, y + height)
            page.insert_textbox(
                box,
                signature_text,
                fontsize=font_size,
                fontname="helv",
                color=(0, 0, 0),
                align=fitz.TEXT_ALIGN_CENTER,
            )
            document.save(output_path)

        logger_user.info(f"PDF firmado guardado en: {output_path}")
        return output_path

    @staticmethod
    def sign_pdf_with_image(
        input_pdf: str | Path,
        output_pdf: str | Path,
        signature_image: str | Path,
        page_number: int = -1,
        x: float = 72,
        y: float = 72,
        width: float = 180,
        height: float = 80,
        sign_all_pages: bool = False,
    ) -> Path:
        """
        Agrega una firma visual desde una imagen a un PDF.

        La imagen puede ser PNG, JPG o JPEG.
        """
        input_path = TheManipulation._validate_existing_file(input_pdf, (".pdf",))
        image_path = TheManipulation._validate_existing_file(signature_image, (".png", ".jpg", ".jpeg"))
        output_path = TheManipulation._ensure_output_path(output_pdf)
        TheManipulation._validate_different_output(input_path, output_path)

        with fitz.open(input_path) as document:
            box = fitz.Rect(x, y, x + width, y + height)
            pages = document if sign_all_pages else [document[page_number]]
            for page in pages:
                page.insert_image(box, filename=str(image_path))
            document.save(output_path)

        logger_user.info(f"PDF firmado guardado en: {output_path}")
        return output_path

    @staticmethod
    def sign_pdf(
        input_pdf: str | Path,
        output_pdf: str | Path,
        signature_text: str | None = None,
        signature_image: str | Path | None = None,
        signature_location: tuple[float, float] = (72, 72),
        page_number: int = -1,
        sign_all_pages: bool = False,
    ) -> Path:
        """
        Agrega una firma visual a un PDF usando texto o imagen.

        Args:
            input_pdf: Ruta del archivo PDF original.
            output_pdf: Ruta donde se guardara el PDF firmado.
            signature_text: Texto que se usara como firma visual.
            signature_image: Ruta de la imagen que se usara como firma visual.
            signature_location: Coordenadas ``(x, y)`` donde iniciara la firma
                dentro de la pagina. PyMuPDF usa puntos PDF; 72 puntos equivalen
                aproximadamente a una pulgada.
            page_number: Numero de pagina donde se ubicara la firma. Por defecto
                usa ``-1`` para firmar la ultima pagina.
            sign_all_pages: Si es ``True``, ubica la firma en todas las paginas.

        Returns:
            Path: Ruta del PDF firmado.
        """
        if len(signature_location) != 2:
            raise ValueError("signature_location debe tener el formato (x, y).")

        x_coordinate, y_coordinate = signature_location

        if signature_image:
            return TheManipulation.sign_pdf_with_image(
                input_pdf=input_pdf,
                output_pdf=output_pdf,
                signature_image=signature_image,
                page_number=page_number,
                x=x_coordinate,
                y=y_coordinate,
                sign_all_pages=sign_all_pages,
            )
        if signature_text:
            return TheManipulation.sign_pdf_with_text(
                input_pdf=input_pdf,
                output_pdf=output_pdf,
                signature_text=signature_text,
                page_number=page_number,
                x=x_coordinate,
                y=y_coordinate,
            )
        raise ValueError("Debe indicar signature_text o signature_image.")

    @staticmethod
    def transform_docx_2_pdf(origin_docx: str | Path, output_file: str | Path) -> Path:
        """
        Convierte un archivo Word .docx a PDF usando Microsoft Word.
        """
        origin_path = TheManipulation._validate_existing_file(origin_docx, (".docx",))
        output_path = TheManipulation._ensure_output_path(output_file)
        TheManipulation._validate_different_output(origin_path, output_path)
        word = None
        doc = None
        com_initialized = False

        try:
            comtypes.CoInitialize()
            com_initialized = True
            word = comtypes.client.CreateObject("Word.Application")
            word.Visible = False
            doc = word.Documents.Open(str(origin_path), ReadOnly=True)
            doc.SaveAs(str(output_path), FileFormat=17)
        finally:
            if doc is not None:
                doc.Close(False)
            if word is not None:
                word.Quit()
            if com_initialized:
                comtypes.CoUninitialize()

        logger_user.info(f"PDF generado desde Word: {output_path}")
        return output_path

    @staticmethod
    def transform_xlsx_2_pdf(origin_xlsx: str | Path, output_file: str | Path) -> Path:
        """
        Convierte un archivo Excel .xlsx a PDF usando Microsoft Excel.
        """
        origin_path = TheManipulation._validate_existing_file(origin_xlsx, (".xlsx",))
        output_path = TheManipulation._ensure_output_path(output_file)
        TheManipulation._validate_different_output(origin_path, output_path)
        excel = None
        workbook = None
        com_initialized = False

        try:
            comtypes.CoInitialize()
            com_initialized = True
            excel = comtypes.client.CreateObject("Excel.Application")
            excel.Visible = False
            workbook = excel.Workbooks.Open(str(origin_path), ReadOnly=True)
            workbook.ExportAsFixedFormat(0, str(output_path))
        finally:
            if workbook is not None:
                workbook.Close(False)
            if excel is not None:
                excel.Quit()
            if com_initialized:
                comtypes.CoUninitialize()

        logger_user.info(f"PDF generado desde Excel: {output_path}")
        return output_path

    @staticmethod
    def transform_office_2_pdf(origin_file: str | Path, output_file: str | Path) -> Path:
        """
        Convierte un archivo .docx o .xlsx a PDF segun su extension.
        """
        origin_path = TheManipulation._as_path(origin_file)
        if origin_path.suffix.lower() == ".docx":
            return TheManipulation.transform_docx_2_pdf(origin_path, output_file)
        if origin_path.suffix.lower() == ".xlsx":
            return TheManipulation.transform_xlsx_2_pdf(origin_path, output_file)
        raise ValueError("Solo se pueden transformar archivos .docx o .xlsx.")


class TheConfigurations:
    """
    Clase que almacena las funciones de configuracion.
    """

    @staticmethod
    def obtain_config_ini(config_file_ini: str, section: str, option: str) -> str | bool:
        """
        De un archivo .ini obtiene el valor de la option en determinada seccion.
        """
        config = configparser.ConfigParser()
        base_name = os.path.basename(config_file_ini)
        if os.path.exists(config_file_ini):
            try:
                config.read(config_file_ini, encoding="utf-8")
                return config.get(section, option)
            except configparser.NoSectionError:
                logger_dev.error(f"This section '{section}' was not found in {base_name} file")
                return False
            except configparser.NoOptionError:
                logger_dev.error(f"This option in '{option}' was not found {base_name} file")
                return False
        logger_dev.error(f"The {base_name} file does not exist")
        return False

    @staticmethod
    def obtain_config_json(config_file_json: str, option: str) -> str | bool:
        """
        De un archivo .json obtiene el valor de la opcion.
        """
        base_name = os.path.basename(config_file_json)
        if os.path.exists(config_file_json):
            try:
                with open(config_file_json, mode="r", encoding="utf-8") as cnf:
                    json_data = json.load(cnf)
                    value = json_data.get(option)
                    if value is None:
                        logger_dev.error(f"This option '{option}' in {base_name} file was not found")
                        return False
                    return value
            except json.JSONDecodeError:
                logger_dev.error("This JSON file has an incorrect format")
                return False
        logger_dev.error(f"The {base_name} file does not exist")
        return False


class TheExecution:
    """
    Clase para hacer llamado a los modulos y funciones por medio de la consola.
    """

    @staticmethod
    def show_help() -> None:
        """
        Funcion que abre la documentacion sobre la ejecucion del script.
        """
        with open(os.path.join(path_to_config, "user_general_conf.json"), "r", encoding="utf-8") as cnf:
            json_data = json.load(cnf)
        if json_data["is_dev"] is True:
            gnu_file = os.path.join(path_to_docs, "GNU_DOC.org")
            if os.path.exists(gnu_file):
                with open(gnu_file, "r", encoding="utf-8") as file:
                    print(file.read())
            else:
                logger_dev.error("GNU documentation file does not exist")
        else:
            logger_dev.error("You are not a dev.")

    @staticmethod
    def execute_gui() -> None:
        import gui

        gui.TheGui.run_gui()

    @staticmethod
    def execution(action: str) -> None:
        """
        Ejecuta funciones basandose en un argumento proporcionado.
        """
        try:
            if action in TheExecution.__DICT_ACTIONS__:
                functions = TheExecution.__DICT_ACTIONS__[action]
                if isinstance(functions, list):
                    [func() for func in functions]
                else:
                    functions()
            else:
                logger_dev.error(f"Accion desconocida: '{action}'")
        except ValueError as e:
            logger_dev.error(e)

    __DICT_ACTIONS__: dict[str, object] = {
        "--help": show_help,
        "-h": show_help,
        "--gui": execute_gui,
        "-g": execute_gui,
    }


if __name__ == "__main__":
    pass
