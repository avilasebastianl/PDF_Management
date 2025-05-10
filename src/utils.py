"""
    Modulo principal de clases, funciones y metodos
"""

import os
import sys
import json
import logging
import logging.config
from datetime import datetime
import time
import random
import string
import configparser
import shutil
import warnings
import sqlite3
import subprocess
import comtypes.client

import yaml
from urllib.parse import quote
import win32com.client as win32
from tabulate import tabulate
from fpdf import FPDF
from PyPDF2 import PdfReader, PdfWriter,PdfMerger
from PIL import Image, ImageTk
from sqlalchemy import create_engine, engine, text

from paths import *

# * Configuracion de logger
with open(os.path.join(path_to_config,"logger.yml"),encoding="utf-8") as f:
    logging.config.dictConfig(yaml.safe_load(f))

logger_user = logging.getLogger("user")
logger_dev = logging.getLogger("dev")

class TheManipulation:

    def join_pdf_files(pdf_files: list[str], pdf_output: str) -> None:
        """Concatena archivos PDF a partir de una lista dada
        si dentro de la lista hay elementos diferentes a .pdf
        se elimina de la lista. Si algun archivo no existe,
        se eliminara de la lista

        Args:
            pdf_files (list[str]): Lista de archivos PDF a concatenar.
            pdf_output (str): Ruta y nombre del archivo PDF final concatenado.
        """
        try:
            base_name_output = os.path.basename(pdf_output)
            dir_name_output = os.path.dirname(pdf_output)
            if not os.path.isdir(dir_name_output):
                logger_dev.error(f"Target folder does not exist, choose again")
                return
            valid_pdfs = []
            invalid_files =  []
            for _file in pdf_files:
                base_name = os.path.basename(_file)
                if not os.path.exists(_file):
                    logger_dev.warning(f"{base_name} does not exist, it won't be concatenated in output")
                    invalid_files.append(_file)
                    continue
                if not _file.lower().endswith('.pdf'):
                    logger_dev.warning(f"{base_name} is not a pdf file, it won't be concatenated in output")
                    invalid_files.append(_file)
                    continue
                valid_pdfs.append(_file)

            logger_user.warning(f"{invalid_files=}")

            merger = PdfMerger()
            logger_user.debug(f"{valid_pdfs=}")
            [ merger.append(archivo) for archivo in valid_pdfs ]
            merger.write(fileobj=pdf_output)
            merger.close()
            logger_user.info(f"'{base_name_output}' was saved in '{dir_name_output}'")
        except ValueError as e:
            logger_dev.error(f"function -> join_pdf_files: {e}")

    def transform_docx_2_pdf(origin_docx:str,output_file:str):
        """
        Convierte un archivo Word a PDF

        Args:
            origin_docx (str): Ruta completa al archivo de word de origen a convertir
            output_file (str): Ruta y nombre del archivo pdf convertido.
        """
        # * Comprobar la existencia del archivo Word
        if not os.path.exists(origin_docx):
            logging.getLogger("user").error(f"Word file '{os.path.basename(origin_docx)}' does not exist.")
            return
        logging.getLogger("user").debug(f"Generating PDF from '{origin_docx}'.")
        try:
            word = comtypes.client.CreateObject("Word.Application")
            doc = word.Documents.Open(origin_docx,ReadOnly=True)
            doc.SaveAs(output_file, FileFormat=17) # * comtypes.client.constants.wdExportFormatPDF -> codigo 17
            doc.Close(False)
        except ValueError as e:
            logging.getLogger("dev").error(f"Could not convert '{origin_docx}' to PDF: {e}")
            return
        finally:
            # * Liberar recursos de Word
            if 'word' in locals():
                word.Quit()

class TheConfigurations:
    """
        Clase que almacena las funciones que 
    """

    def obtain_config_ini(config_file_ini:str, section:str, option:str) -> str|bool:
        """
        De un archivo .ini obtiene el valor de la option en determinada
        seccion

        Args:
            config_file_ini (str): Ruta completa al archivo .ini
            section (str): Seccion a acceder dentro del archivo .ini
            option (str): Opcion dentro de la seccion a acceder dentro del archivo .ini

        Returns:
            str|bool: Valor de la option de la seccion. Si no encuentra un valor, retorna False
        """
        config = configparser.ConfigParser()
        base_name = os.path.basename(config_file_ini)
        if os.path.exists(config_file_ini):
            try:
                config.read(config_file_ini,encoding='utf-8')
                return config.get(section, option)
            except configparser.NoSectionError:
                logger_dev.error(f"This section '{section}' was not found in {base_name} file")
                return False
            except configparser.NoOptionError:
                logger_dev.error(f"This option in '{option}' was not found {base_name} file")
                return False
        else:
            logger_dev.error(f"The {base_name} file does not exist")
            return False

    def obtain_config_json(config_file_json:str,option:str) -> str|bool:
        """
        De un archivo .json obtiene el valor de la opcion

        Args:
            config_file_json (str): Ruta completa al archivo .json
            option (str): Opcion a acceder dentro del archivo .json

        Returns:
            str|bool: Valor de la opcion. Si no encuentra un valor, retorna False
        """
        base_name = os.path.basename(config_file_json)
        if os.path.exists(config_file_json):
            try:
                with open(config_file_json,mode='r',encoding='utf-8') as cnf:
                    json_data = json.load(cnf)
                    _value = json_data.get(option)
                    if _value is None:
                        logger_dev.error(f"This option '{option}' in {base_name} file was not found")
                        return False
                    return json_data[option]
            except json.JSONDecodeError:
                logger_dev.error(f"This JSON file has an incorrect format")
                return False
        else:
            logger_dev.error(f"The {base_name} file does not exist")
            return False

class TheExecution:
    """
        Clase para hacer llamado a los modulos y
        funciones y comprenden el desarrollo
        por medio de la consola
    """

    # * Funcion de mostrar ayuda
    def show_help() -> None:
        """
            Funcion que abre la documentacion sobre la ejecucion del script
            para desarrolladores
        """
        with open(os.path.join(path_to_config,"user_general_conf.json"),'r',encoding='utf-8') as cnf:
            json_data = json.load(cnf)
        if json_data["is_dev"] == True:
            gnu_file = os.path.join(path_to_docs,"GNU_DOC.org")
            if os.path.exists(gnu_file):
                with open(gnu_file,'r',encoding='utf-8') as file:
                    print(file.read())
            else:
                logger_dev.error("GNU documentation file does not exist")
        else:
            logger_dev.error("You are not a dev.")

    # * Main
    def execution(action:str) -> None:
        """
        Ejecuta funciones basándose en un argumento proporcionado.

        Args:
            action (str): La acción a ejecutar.

        Raises:
            ValueError: Si la acción no está definida.
        """
        try:
            if action in TheExecution.__DICT_ACTIONS__:
                functions = TheExecution.__DICT_ACTIONS__[action]
                if isinstance(functions, list):
                    [func() for func in functions]
                else:
                    functions()
            else:
                logger_dev.error(f"Acción desconocida: '{action}'")
        except ValueError as e:
            logger_dev.error(e)

    __DICT_ACTIONS__: dict[str:str] = {
        '--help' : show_help,
        '-h' : show_help
    }

if __name__ == '__main__':
    pass
