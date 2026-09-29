"""
Modulo de despliegue para configurar la aplicacion
en nuevos dispositivos
"""
import os
import sys
import ctypes
import paths

options:list[str] = sys.argv # * Todos los comandos u opciones que se pasan por argumento de sistema

class TheDeployment:
    """Clase que configura los requerimientos para ejecutar
    el script correctamente
    """

    # *  Funcion que configura el logger basado en la maqueta
    def build_logger(self) -> None:
        """
            Crea el archivo final de configuracion logger
        """
        print("Creating logger")
        with open(paths.join_func(paths.config_path, "logger_maket.yml"), 'r',
                  encoding="latin-1") as logg:
            build = logg.read()
        build = build.format(path_to_logs=paths.path_to_logs)
        with open(paths.join_func(paths.path_to_config, "logger.yml"), 'w',
                  encoding="latin-1") as logg:
            logg.write(build)
        print("Logger configuration file ready")

    # * Generar acceso directo en el escritorio del usuario
    def create_hyperlink(self) -> None:
        """
            Genera el hipervinculo a la ejecucion de la GUI
            en el escritorio del usuario.
        """
        if '--create-shortcuts=True' in options:
            with open(os.path.join(paths.config_path,"execute.txt"), 'r',encoding="utf-8") as cons:
                bat = cons.read()
            bat = bat.format(project_directory=paths.project_directory)
            with open(paths.join_func(paths.path_to_bin, "Logistica-TNS.bat"), 'w', encoding="utf-8") as cons:
                cons.write(bat)
            print("Execution file created")

            buf = ctypes.create_unicode_buffer(512)
            ctypes.windll.shell32.SHGetFolderPathW(None, 0x00000000, None, 0, buf)
            desktop_path = buf.value
            hiperlink_path = os.path.join(desktop_path,"Logistica-TNS.url")
            path_to_bat = os.path.join(paths.path_to_bin,"Logistica-TNS.bat")
            icon_path = os.path.join(paths.path_to_assets,"NAOS-ICO.ico")

            # * Crear archivo .url
            contenido = f"""[InternetShortcut]
                            URL=file:///{path_to_bat.replace("\\", "/")}
                            IconFile={icon_path}
                            IconIndex=0
                        """
            with open(hiperlink_path, "w",encoding='utf-8') as acceso:
                acceso.write(contenido)

            # * Marcar como acceso directo en Windows
            ctypes.windll.kernel32.SetFileAttributesW(hiperlink_path, 0x800)
            print("Desktop hiperlink file created")
        elif '--create-shortcuts=False' in options:
            print("No shortcut was created...")
        else:
            print("No shortcut option was given as an argument...")

    # * Generar el archivo de configuracion de dimension de gui
    def make_app_option(self) -> None:
        """
            Escribe la dimension de la ventana principal
        """
        _height_:int=320
        _width_:int=1000
        _theme_:str="Dark"
        _color_theme_:str="red"
        content = f"[Size]\nwidth={_width_}\nheight={_height_}\n[Theme]\ntheme={_theme_}\ncolor_theme={_color_theme_}"
        with open(os.path.join(paths.path_to_config,"default.ini"), "w", encoding="utf-8") as f:
            f.write(content)

    # * formatea el archivo plantilla con la ubicacion del proyecto
    def make_update_file(self) -> None:
        """
            Crea archivo binario de ejecucion de actualizacion de la aplicacion
        """
        with open(os.path.join(paths.config_path,"update.txt"),"r",encoding="utf-8") as upt:
            bat = upt.read()
        bat = bat.format(project_directory=paths.project_directory)
        with open(os.path.join(paths.path_to_bin,"update-app.bat"),"w",encoding="utf-8") as bin:
            bin.write(bat)

if __name__ == '__main__':
    deployer = TheDeployment()
    # deployer.build_logger()
    # deployer.create_hyperlink()
    deployer.make_app_option()
    # deployer.make_update_file()
    print("┌───────────────────────────────────────┐")
    print("│                SUCCESS                │")
    print("└───────────────────────────────────────┘")
