"""
Modulo de rutas constantes de cada carpeta del proyectos
"""
import os
from pathlib import Path

script_directory:Path = Path(__file__).parent.absolute()
project_directory:Path = script_directory.parent
path_to_config:Path = project_directory / "config"
config_path:Path = project_directory / ".config"
path_to_logs:Path = project_directory / "log"
path_to_data:Path = project_directory / "data"
path_to_docs:Path = project_directory / "docs"
path_to_bin:Path = project_directory / "bin"
path_to_assets:Path = project_directory / "assets"
path_to_output:Path = project_directory / "out"
path_to_locale:Path = project_directory / "locale"
path_to_database:Path = project_directory / "database"
path_to_sql:Path = project_directory / "sql"
path_to_lib:Path = project_directory / "lib"
path_to_export:Path = project_directory / "export"
path_to_share:Path = project_directory / "share"

if __name__ == '__main__':
    pass # ! No borre esta linea de codigo, realice pruebas abajo