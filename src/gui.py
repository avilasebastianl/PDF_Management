"""
Interfaz grafica principal para PDF Management.
"""

import logging
import os
import shutil
import sys
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
from typing import Callable

import customtkinter as ctk
import pymupdf as fitz
from PIL import Image, ImageDraw, ImageTk
from tkinterdnd2 import DND_FILES, TkinterDnD

import paths
import utils
from utils import TheConfigurations, TheManipulation

APP_DEFAULT_SETTINGS_FILE = paths.path_to_config / "default.ini"
MAIN_ICON = paths.path_to_assets / "icons" / "icon_wnd.ico"
DELETE_IMAGE = paths.path_to_assets / "images" / "delete.png"
UP_IMAGE = paths.path_to_assets / "images" / "up.png"
DOWN_IMAGE = paths.path_to_assets / "images" / "down.png"
NEXT_IMAGE = paths.path_to_assets / "images" / "next.png"
PREVIOUS_IMAGE = paths.path_to_assets / "images" / "previous.png"
PLUS_IMAGE = paths.path_to_assets / "images" / "plus.png"
MINUS_IMAGE = paths.path_to_assets / "images" / "minus.png"
RESET_IMAGE = paths.path_to_assets / "images" / "reset.png"
QR_IMAGE = paths.path_to_assets / "images" / "qr_v2.png"
HELP_ICON = paths.path_to_assets / "icons" / "help.ico"
PENCIL_ICON = paths.path_to_assets / "icons" / "pencil.ico"
USER_GUIDE_FILE = paths.path_to_docs / "user_guide.md"

WINDOW_HEIGHT = int(
    TheConfigurations.obtain_config_ini(
        config_file_ini=str(APP_DEFAULT_SETTINGS_FILE),
        section="Size",
        option="height",
    )
)
WINDOW_WIDTH = int(
    TheConfigurations.obtain_config_ini(
        config_file_ini=str(APP_DEFAULT_SETTINGS_FILE),
        section="Size",
        option="width",
    )
)
APP_THEME = TheConfigurations.obtain_config_ini(
    config_file_ini=str(APP_DEFAULT_SETTINGS_FILE),
    section="Theme",
    option="theme",
)
COLOR_THEME = TheConfigurations.obtain_config_ini(
    config_file_ini=str(APP_DEFAULT_SETTINGS_FILE),
    section="Theme",
    option="color_theme",
)
BACKGROUND_COLOR = TheConfigurations.obtain_config_ini(
    config_file_ini=str(APP_DEFAULT_SETTINGS_FILE),
    section="Theme",
    option="background",
)
INITIAL_WINDOW = TheConfigurations.obtain_config_ini(
    config_file_ini=str(APP_DEFAULT_SETTINGS_FILE),
    section="App",
    option="initial_window",
)
APP_VERSION = (paths.path_to_locale / "Version").read_text(encoding="utf-8")


def _get_config_float(section: str, option: str, default: float) -> float:
    value = TheConfigurations.obtain_config_ini(
        config_file_ini=str(APP_DEFAULT_SETTINGS_FILE),
        section=section,
        option=option,
    )
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_config_bool(section: str, option: str, default: bool) -> bool:
    value = TheConfigurations.obtain_config_ini(
        config_file_ini=str(APP_DEFAULT_SETTINGS_FILE),
        section=section,
        option=option,
    )
    if isinstance(value, str):
        return value.strip().lower() in ("1", "yes", "true", "si", "sí")
    return default

UI_SCALING = _get_config_float("Display", "ui_scaling", 1.0)
OPEN_AFTER_SAVE = _get_config_bool("Display", "open_after_save", True)

TAB_ALIASES = {
    "Unificar PDFs": "Unir",
    "Desunir PDF": "Extraer",
    "Transformar a PDF": "Convertir",
    "Firmar PDF": "Firmar",
    "Seguridad PDF": "Proteger",
    "Configuraciones": "Ajustes",
}

logger_user = logging.getLogger("user")
logger_dev = logging.getLogger("dev")


class PdfManagementGui:
    """
    Construye y controla la interfaz principal de la aplicacion.
    """

    tabs = [
        "Unir",
        "Extraer",
        "Convertir",
        "Firmar",
        "Proteger",
        "Ajustes",
    ]

    def __init__(self) -> None:
        self.root = TkinterDnD.Tk()
        self.task_executor = ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="pdf-management",
        )
        self.pending_task_count = 0
        self.status_message = tk.StringVar(value="Listo para procesar archivos")
        self.delete_icon = self._load_image(image_path=DELETE_IMAGE)
        self.up_icon = self._load_image(image_path=UP_IMAGE)
        self.down_icon = self._load_image(image_path=DOWN_IMAGE)
        self.pdf_files: list[Path] = []
        self.file_widgets: dict[Path, ctk.CTkFrame] = {}

        self.split_pdf_file = tk.StringVar(value="")
        self.split_output_file = tk.StringVar(value="")
        self.split_pages = tk.StringVar(value="")
        self.split_password = tk.StringVar(value="")
        self.split_output_password = tk.StringVar(value="")
        self.split_page_count = tk.StringVar(value="Seleccione un PDF")

        self.office_file = tk.StringVar(value="")
        self.office_output = tk.StringVar(value="")

        self.minus_icon = self._load_image(image_path=MINUS_IMAGE)
        self.plus_icon = self._load_image(image_path=PLUS_IMAGE)
        self.current_theme = tk.StringVar(value=str(APP_THEME))
        self.current_scaling = tk.DoubleVar(value=UI_SCALING)
        self.scaling_label = tk.StringVar(value=f"{int(UI_SCALING * 100)}%")
        self.open_after_save = tk.StringVar(
            value="Si" if OPEN_AFTER_SAVE else "No"
        )

        self.sign_pdf_file = tk.StringVar(value="")
        self.sign_output_file = tk.StringVar(value="")
        self.signature_image = tk.StringVar(value="")
        self.signature_image_label = tk.StringVar(value="Sin imagen")
        self.signature_image_paths: dict[str, Path] = {}
        self.previous_icon = self._load_image(image_path=PREVIOUS_IMAGE)
        self.next_icon = self._load_image(image_path=NEXT_IMAGE)
        self.reset_icon = self._load_image(image_path=RESET_IMAGE)
        self.signature_preview_image = None
        self.signature_source_image: Image.Image | None = None
        self.sign_overlay_image = None
        self.signature_x = tk.StringVar(value="72")
        self.signature_y = tk.StringVar(value="720")
        self.signature_page = tk.StringVar(value="0")
        self.sign_all_pages = tk.BooleanVar(value=False)
        self.sign_preview_image = None
        self.sign_preview_scale = 1.0
        self.sign_preview_page_origin = (0.0, 0.0)
        self.sign_preview_zoom = 1.0
        self.sign_preview_page_index = 0
        self.sign_preview_page_count = 0
        self.signature_image.trace_add("write", self._on_signature_image_changed)

        self.security_mode = tk.StringVar(value="Bloquear")
        self.security_pdf_file = tk.StringVar(value="")
        self.security_output_file = tk.StringVar(value="")
        self.security_password = tk.StringVar(value="")

    @classmethod
    def run_gui(cls) -> None:
        """
        Inicia la ventana principal de la aplicacion.
        """
        app = cls()
        app.run()

    def run(self) -> None:
        """
        Configura la ventana principal y ejecuta el bucle de eventos.
        """
        self._configure_root()
        self._build_menu()
        self._build_tabs()
        self.root.mainloop()

    def _configure_root(self) -> None:
        self.root.title("PDF Management")
        self._center_window(self.root, WINDOW_WIDTH, WINDOW_HEIGHT)
        self.root.minsize(980, 620)
        self.root.resizable(True, True)
        self.root.configure(bg=BACKGROUND_COLOR)
        self.root.protocol("WM_DELETE_WINDOW", self._exit_program)

        ctk.set_appearance_mode(APP_THEME)
        ctk.set_widget_scaling(UI_SCALING)
        ctk.set_default_color_theme(
            str(paths.path_to_assets / "json" / f"{COLOR_THEME}.json")
        )

        if MAIN_ICON.exists():
            self.root.iconbitmap(str(MAIN_ICON))

    def _build_menu(self) -> None:
        header = ctk.CTkFrame(self.root, corner_radius=0)
        header.pack(fill="x")
        header.grid_columnconfigure(1, weight=1)

        left_header = ctk.CTkFrame(header, fg_color="transparent")
        left_header.grid(row=0, column=0, sticky="w", padx=10, pady=6)

        right_header = ctk.CTkFrame(header, fg_color="transparent")
        right_header.grid(row=0, column=2, sticky="e", padx=10, pady=6)

        brand_label = ctk.CTkLabel(
            left_header,
            text="PDF Management",
            font=("Segoe UI", 18, "bold"),
        )
        brand_label.pack(side="left", padx=(4, 18))

        help_button = ctk.CTkButton(
            left_header,
            text="Ayuda",
            width=86,
            fg_color="transparent",
            border_width=1,
            command=self._open_help_window,
        )
        help_button.pack(side="left")
        ToolTip(help_button, "Abrir guia de uso")

        self.theme_switch = ctk.CTkSwitch(
            right_header,
            text="Light",
            command=self._toggle_theme,
        )
        self.theme_switch.pack(side="left", padx=(0, 12))
        if str(APP_THEME).lower() == "light":
            self.theme_switch.select()
        else:
            self.theme_switch.configure(text="Dark")

        scale_down_button = ctk.CTkButton(
            right_header,
            text="",
            image=self.minus_icon,
            width=34,
            command=lambda: self._change_ui_scaling(-0.05),
        )
        scale_down_button.pack(side="left")
        ToolTip(scale_down_button, "Reducir escala de interfaz")

        scale_label = ctk.CTkLabel(
            right_header,
            textvariable=self.scaling_label,
            width=54,
        )
        scale_label.pack(side="left", padx=4)

        scale_up_button = ctk.CTkButton(
            right_header,
            text="",
            image=self.plus_icon,
            width=34,
            command=lambda: self._change_ui_scaling(0.05),
        )
        scale_up_button.pack(side="left")
        ToolTip(scale_up_button, "Aumentar escala de interfaz")

    def _build_tabs(self) -> None:
        tabview = ctk.CTkTabview(master=self.root)
        tabview.pack(padx=16, pady=12, fill="both", expand=True)

        for tab_name in self.tabs:
            tabview.add(tab_name)

        initial_tab = TAB_ALIASES.get(str(INITIAL_WINDOW), str(INITIAL_WINDOW))
        if initial_tab in self.tabs:
            tabview.set(initial_tab)

        self._build_merge_tab(tabview.tab("Unir"))
        self._build_split_tab(tabview.tab("Extraer"))
        self._build_convert_tab(tabview.tab("Convertir"))
        self._build_sign_tab(tabview.tab("Firmar"))
        self._build_security_tab(tabview.tab("Proteger"))
        self._build_settings_tab(tabview.tab("Ajustes"))

        footer = ctk.CTkFrame(self.root, corner_radius=0, fg_color="transparent")
        footer.pack(fill="x", pady=(0, 6))
        footer.grid_columnconfigure(0, weight=1)
        footer.grid_columnconfigure(2, weight=1)

        status_frame = ctk.CTkFrame(footer, fg_color="transparent")
        status_frame.grid(row=0, column=0, sticky="w", padx=16)
        self.activity_progress = ctk.CTkProgressBar(
            status_frame,
            width=84,
            height=6,
            mode="indeterminate",
        )
        self.activity_progress.pack(side="left", padx=(0, 8))
        self.activity_progress.set(0)
        status_label = ctk.CTkLabel(
            status_frame,
            textvariable=self.status_message,
            font=("Segoe UI", 11),
        )
        status_label.pack(side="left")

        version_label = ctk.CTkLabel(footer, text=APP_VERSION.strip(), anchor="center")
        version_label.grid(row=0, column=1)

    def _build_merge_tab(self, parent: ctk.CTkFrame) -> None:
        frame = self._content_frame(parent)
        self._title(frame, "Unir PDFs")

        actions = ctk.CTkFrame(frame, corner_radius=8)
        actions.pack(fill="x", padx=16, pady=(8, 12))

        add_button = ctk.CTkButton(
            actions,
            text="Agregar PDFs",
            command=self._select_pdf_files_to_merge,
        )
        add_button.pack(side="left", padx=10, pady=10)

        clear_button = ctk.CTkButton(
            actions,
            text="Limpiar lista",
            fg_color="transparent",
            border_width=1,
            command=self._clear_merge_files,
        )
        clear_button.pack(side="left", padx=8, pady=10)

        self.merge_output_entry = self._path_entry(
            actions,
            "Archivo de salida",
            paths.path_to_export / "salida.pdf",
            self._select_merge_output,
        )

        self.merge_files_frame = ctk.CTkScrollableFrame(frame, border_width=1)
        self.merge_files_frame.pack(fill="both", expand=True, padx=16, pady=8)
        self._register_merge_drop_target(frame)
        self._register_merge_drop_target(actions)
        self._register_merge_drop_target(self.merge_files_frame)
        if hasattr(self.merge_files_frame, "_parent_canvas"):
            self._register_merge_drop_target(self.merge_files_frame._parent_canvas)

        run_button = ctk.CTkButton(
            frame,
            text="Unir PDFs",
            command=self._merge_pdf_files,
        )
        run_button.pack(anchor="e", padx=16, pady=12)

    def _register_merge_drop_target(self, widget) -> None:
        widget.drop_target_register(DND_FILES)
        widget.dnd_bind("<<Drop>>", self._drop_merge_files)

    def _build_split_tab(self, parent: ctk.CTkFrame) -> None:
        frame = self._content_frame(parent)
        self._title(frame, "Extraer paginas")

        form = self._form_frame(frame)
        self._file_row(
            form,
            row=0,
            label="PDF origen",
            variable=self.split_pdf_file,
            command=self._select_split_pdf,
        )
        self._file_row(
            form,
            row=1,
            label="PDF de salida",
            variable=self.split_output_file,
            command=self._select_split_output,
        )
        self._entry_row(
            form,
            row=2,
            label="Paginas",
            variable=self.split_pages,
        )
        self._entry_row(
            form,
            row=3,
            label="Clave PDF origen",
            variable=self.split_password,
            show="*",
        )
        self._entry_row(
            form,
            row=4,
            label="Clave PDF final",
            variable=self.split_output_password,
            show="*",
        )

        info_frame = ctk.CTkFrame(frame, corner_radius=8)
        info_frame.pack(fill="x", padx=16, pady=(0, 12))

        page_count_label = ctk.CTkLabel(
            info_frame,
            textvariable=self.split_page_count,
            anchor="w",
        )
        page_count_label.pack(fill="x", padx=12, pady=(10, 4))

        example_label = ctk.CTkLabel(
            info_frame,
            text="Ejemplos: 2,4,7,9   |   1-3,8,10   |   all/todo   |   impar/odd   |   par/even",
            anchor="w",
        )
        example_label.pack(fill="x", padx=12, pady=(0, 10))

        run_button = ctk.CTkButton(
            frame,
            text="Crear PDF",
            command=self._split_pdf_file,
        )
        run_button.pack(anchor="e", padx=16, pady=12)

    def _build_convert_tab(self, parent: ctk.CTkFrame) -> None:
        frame = self._content_frame(parent)
        self._title(frame, "Convertir a PDF")

        form = self._form_frame(frame)
        self._file_row(
            form,
            row=0,
            label="Archivo .docx o .xlsx",
            variable=self.office_file,
            command=self._select_office_file,
        )
        self._file_row(
            form,
            row=1,
            label="PDF de salida",
            variable=self.office_output,
            command=self._select_office_output,
        )

        run_button = ctk.CTkButton(
            frame,
            text="Convertir",
            command=self._convert_office_file,
        )
        run_button.pack(anchor="e", padx=16, pady=12)

    def _build_sign_tab(self, parent: ctk.CTkFrame) -> None:
        frame = self._content_frame(parent)
        self._title(frame, "Firmar")

        workspace = ctk.CTkFrame(frame, fg_color="transparent")
        workspace.pack(fill="both", expand=True, padx=16, pady=12)
        workspace.grid_columnconfigure(0, weight=0)
        workspace.grid_columnconfigure(1, weight=1)
        workspace.grid_rowconfigure(0, weight=1)

        form = ctk.CTkFrame(workspace, corner_radius=8, width=390)
        form.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        form.grid_columnconfigure(1, weight=1)

        viewer = ctk.CTkFrame(workspace, corner_radius=8)
        viewer.grid(row=0, column=1, sticky="nsew")
        viewer.grid_columnconfigure(0, weight=1)
        viewer.grid_rowconfigure(1, weight=1)

        self._file_row(
            form,
            row=0,
            label="PDF a firmar",
            variable=self.sign_pdf_file,
            command=self._select_sign_pdf,
        )
        self._file_row(
            form,
            row=1,
            label="PDF firmado",
            variable=self.sign_output_file,
            command=self._select_sign_output,
        )

        self._signature_image_row(form, row=2)

        self.signature_preview_label = ctk.CTkLabel(
            form,
            text="Vista previa",
            width=260,
            height=110,
            fg_color="white",
            text_color="black",
            corner_radius=8,
        )
        self.signature_preview_label.grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=10,
            pady=(0, 10),
        )

        signature_button = ctk.CTkButton(
            form,
            text="Crear firma",
            command=self._open_signature_window,
        )
        signature_button.grid(row=4, column=1, sticky="e", padx=10, pady=(0, 8))

        location_frame = ctk.CTkFrame(form, fg_color="transparent")
        location_frame.grid(row=5, column=1, sticky="ew", padx=10, pady=8)
        location_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self._small_entry(location_frame, "X", self.signature_x, 0)
        self._small_entry(location_frame, "Y", self.signature_y, 1)
        self._small_entry(location_frame, "Pagina", self.signature_page, 2)

        location_label = ctk.CTkLabel(form, text="Ubicacion")
        location_label.grid(row=5, column=0, sticky="w", padx=10, pady=8)

        all_pages_checkbox = ctk.CTkCheckBox(
            form,
            text="Firmar todas las hojas",
            variable=self.sign_all_pages,
        )
        all_pages_checkbox.grid(row=6, column=1, sticky="w", padx=10, pady=(0, 8))

        run_button = ctk.CTkButton(
            form,
            text="Firmar",
            command=self._sign_pdf,
        )
        run_button.grid(row=7, column=1, sticky="e", padx=10, pady=12)

        viewer_toolbar = ctk.CTkFrame(viewer, fg_color="transparent")
        viewer_toolbar.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        viewer_toolbar.grid_columnconfigure(2, weight=1)

        first_button = ctk.CTkButton(
            viewer_toolbar,
            text="|<",
            width=42,
            command=lambda: self._go_to_sign_preview_page(0),
        )
        first_button.grid(row=0, column=0, padx=(0, 6))
        ToolTip(first_button, "Primera pagina")

        previous_button = ctk.CTkButton(
            viewer_toolbar,
            text="",
            image=self.previous_icon,
            width=42,
            command=lambda: self._change_sign_preview_page(-1),
        )
        previous_button.grid(row=0, column=1, padx=(0, 6))
        ToolTip(previous_button, "Pagina anterior")

        self.sign_page_label = ctk.CTkLabel(
            viewer_toolbar,
            text="Seleccione un PDF",
            anchor="center",
        )
        self.sign_page_label.grid(row=0, column=2, sticky="ew")

        next_button = ctk.CTkButton(
            viewer_toolbar,
            text="",
            image=self.next_icon,
            width=42,
            command=lambda: self._change_sign_preview_page(1),
        )
        next_button.grid(row=0, column=3, padx=(6, 0))
        ToolTip(next_button, "Siguiente pagina")

        last_button = ctk.CTkButton(
            viewer_toolbar,
            text=">|",
            width=42,
            command=self._go_to_last_sign_preview_page,
        )
        last_button.grid(row=0, column=4, padx=(6, 0))
        ToolTip(last_button, "Ultima pagina")

        zoom_out_button = ctk.CTkButton(
            viewer_toolbar,
            text="",
            image=self.minus_icon,
            width=42,
            command=lambda: self._change_sign_preview_zoom(-0.25),
        )
        zoom_out_button.grid(row=0, column=5, padx=(12, 4))
        ToolTip(zoom_out_button, "Disminuir zoom")

        self.sign_zoom_label = ctk.CTkLabel(
            viewer_toolbar,
            text="100%",
            width=58,
            anchor="center",
        )
        self.sign_zoom_label.grid(row=0, column=6)

        zoom_in_button = ctk.CTkButton(
            viewer_toolbar,
            text="",
            image=self.plus_icon,
            width=42,
            command=lambda: self._change_sign_preview_zoom(0.25),
        )
        zoom_in_button.grid(row=0, column=7, padx=4)
        ToolTip(zoom_in_button, "Aumentar zoom")

        reset_zoom_button = ctk.CTkButton(
            viewer_toolbar,
            text="Reiniciar vista",
            image=self.reset_icon,
            width=54,
            command=self._reset_sign_preview_zoom,
        )
        reset_zoom_button.grid(row=0, column=8, padx=(4, 0))
        ToolTip(reset_zoom_button, "Restablecer zoom")

        self.sign_preview_canvas = tk.Canvas(
            viewer,
            background="#1f1f1f",
            highlightthickness=0,
        )
        self.sign_preview_canvas.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=(0, 0))
        sign_vertical_scroll = tk.Scrollbar(
            viewer,
            orient="vertical",
            command=self.sign_preview_canvas.yview,
        )
        sign_vertical_scroll.grid(row=1, column=1, sticky="ns", padx=(0, 10), pady=(0, 0))

        sign_horizontal_scroll = tk.Scrollbar(
            viewer,
            orient="horizontal",
            command=self.sign_preview_canvas.xview,
        )
        sign_horizontal_scroll.grid(row=2, column=0, sticky="ew", padx=(10, 0), pady=(0, 10))
        self.sign_preview_canvas.configure(
            xscrollcommand=sign_horizontal_scroll.set,
            yscrollcommand=sign_vertical_scroll.set,
        )
        self.sign_preview_canvas.bind("<Button-1>", self._set_signature_location_from_preview)

    def _build_security_tab(self, parent: ctk.CTkFrame) -> None:
        frame = self._content_frame(parent)
        self._title(frame, "Bloquear o desbloquear PDF")

        form = self._form_frame(frame)
        mode_label = ctk.CTkLabel(form, text="Accion")
        mode_label.grid(row=0, column=0, sticky="w", padx=10, pady=8)

        mode_selector = ctk.CTkSegmentedButton(
            form,
            values=["Bloquear", "Desbloquear"],
            variable=self.security_mode,
            command=lambda _: self._set_default_security_output(),
        )
        mode_selector.grid(row=0, column=1, sticky="ew", padx=10, pady=8)

        self._file_row(
            form,
            row=1,
            label="PDF origen",
            variable=self.security_pdf_file,
            command=self._select_security_pdf,
        )
        self._file_row(
            form,
            row=2,
            label="PDF de salida",
            variable=self.security_output_file,
            command=self._select_security_output,
        )
        self._entry_row(
            form,
            row=3,
            label="Contraseña",
            variable=self.security_password,
            show="*",
        )

        run_button = ctk.CTkButton(
            frame,
            text="Ejecutar",
            command=self._run_security_action,
        )
        run_button.pack(anchor="e", padx=16, pady=12)

    def _build_settings_tab(self, parent: ctk.CTkFrame) -> None:
        frame = self._content_frame(parent)
        self._title(frame, "Ajustes")

        workspace = ctk.CTkFrame(frame, fg_color="transparent")
        workspace.pack(fill="both", expand=True, padx=16, pady=12)

        form = ctk.CTkFrame(workspace, corner_radius=8)
        form.place(relx=0.5, rely=0, anchor="n", y=8)
        form.grid_columnconfigure(1, weight=0)

        donation_frame = ctk.CTkFrame(workspace, corner_radius=8)
        donation_frame.place(relx=1, rely=0, anchor="ne", x=-8, y=8)

        donation_title = ctk.CTkLabel(
            donation_frame,
            text="Dona al desarrollador",
            font=("Segoe UI", 16, "bold"),
        )
        donation_title.pack(padx=18, pady=(16, 8))

        if QR_IMAGE.exists():
            qr_image = Image.open(QR_IMAGE)
            qr_image.thumbnail((190, 190))
            self.qr_image = ctk.CTkImage(
                light_image=qr_image,
                dark_image=qr_image,
                size=qr_image.size,
            )
            qr_label = ctk.CTkLabel(donation_frame, text="", image=self.qr_image)
            qr_label.pack(padx=18, pady=(0, 18))
        else:
            qr_label = ctk.CTkLabel(donation_frame, text="QR no encontrado")
            qr_label.pack(padx=18, pady=(0, 18))

        width_var = tk.StringVar(value=str(WINDOW_WIDTH))
        height_var = tk.StringVar(value=str(WINDOW_HEIGHT))
        theme_var = tk.StringVar(value=str(APP_THEME))
        color_var = tk.StringVar(value=str(COLOR_THEME))
        scaling_var = tk.StringVar(value=self._scaling_to_label(UI_SCALING))
        initial_tab_var = tk.StringVar(
            value=TAB_ALIASES.get(str(INITIAL_WINDOW), str(INITIAL_WINDOW))
        )
        open_after_save_var = tk.StringVar(value=self.open_after_save.get())

        self._combo_row(form, 0, "Ancho", width_var, ["800", "1000", "1200", "1400"])
        self._combo_row(form, 1, "Alto", height_var, ["600", "700", "800", "900"])
        self._combo_row(form, 2, "Tema", theme_var, ["Light", "Dark", "System"])
        self._combo_row(
            form,
            3,
            "Color",
            color_var,
            ["Rojo", "Verde", "Lavanda", "Naranja", "AzulOscuro"],
        )
        self._combo_row(form, 4, "Ventana inicial", initial_tab_var, self.tabs)
        self._combo_row(
            form,
            5,
            "Escala UI",
            scaling_var,
            ["75%", "85%", "95%", "100%", "110%", "125%", "150%"],
        )
        self._combo_row(
            form,
            6,
            "Abrir al guardar",
            open_after_save_var,
            ["Si", "No"],
        )

        apply_button = ctk.CTkButton(
            form,
            text="Aplicar cambios",
            command=lambda: self._save_settings(
                width_var.get(),
                height_var.get(),
                theme_var.get(),
                color_var.get(),
                initial_tab_var.get(),
                scaling_var.get(),
                open_after_save_var.get(),
            ),
        )
        apply_button.grid(row=7, column=1, sticky="e", padx=10, pady=14)

    def _select_pdf_files_to_merge(self) -> None:
        files = filedialog.askopenfilenames(
            title="Seleccionar archivos PDF",
            filetypes=(("Archivos PDF", "*.pdf"),),
        )
        self._add_merge_files(files)

    def _drop_merge_files(self, event: tk.Event) -> None:
        files = self.root.tk.splitlist(event.data)
        self._add_merge_files(files)

    def _add_merge_files(self, files: tuple[str, ...] | list[str]) -> None:
        files_added = False
        for file_name in files:
            pdf_path = Path(file_name)
            if pdf_path.suffix.lower() != ".pdf" or pdf_path in self.pdf_files:
                continue
            self.pdf_files.append(pdf_path)
            files_added = True
            self._show_debug(f"Archivo: {pdf_path} añadido a la lista de pdfs por unificar")

        if files_added:
            self._refresh_merge_file_widgets()

    def _refresh_merge_file_widgets(self) -> None:
        for widget in self.file_widgets.values():
            widget.destroy()

        self.file_widgets.clear()

        for index, pdf_path in enumerate(self.pdf_files):
            self._add_merge_file_widget(index, pdf_path)

    def _add_merge_file_widget(self, index: int, pdf_path: Path) -> None:
        row = ctk.CTkFrame(self.merge_files_frame, corner_radius=8)
        row.pack(fill="x", pady=4, padx=4)

        order_label = ctk.CTkLabel(row, text=f"{index + 1:02}", width=34)
        order_label.pack(side="left", padx=(10, 4), pady=8)

        name_label = ctk.CTkLabel(
            row,
            text=str(pdf_path),
            anchor="w",
        )
        name_label.pack(side="left", fill="x", expand=True, padx=10, pady=8)

        down_button = ctk.CTkButton(
            row,
            width=34,
            text="",
            image=self.down_icon,
            state="disabled" if index == len(self.pdf_files) - 1 else "normal",
            command=lambda: self._move_merge_file(pdf_path, 1),
        )
        down_button.pack(side="right", padx=(0, 6), pady=6)

        up_button = ctk.CTkButton(
            row,
            width=34,
            text="",
            image=self.up_icon,
            state="disabled" if index == 0 else "normal",
            command=lambda: self._move_merge_file(pdf_path, -1),
        )
        up_button.pack(side="right", padx=(0, 6), pady=6)

        delete_button = ctk.CTkButton(
            row,
            width=34,
            text="",
            image=self.delete_icon,
            hover_color="darkred",
            command=lambda: self._remove_merge_file(pdf_path),
        )
        delete_button.pack(side="right", padx=6, pady=6)
        self.file_widgets[pdf_path] = row

    def _move_merge_file(self, pdf_path: Path, offset: int) -> None:
        current_index = self.pdf_files.index(pdf_path)
        new_index = current_index + offset

        if new_index < 0 or new_index >= len(self.pdf_files):
            return

        self.pdf_files[current_index], self.pdf_files[new_index] = (
            self.pdf_files[new_index],
            self.pdf_files[current_index],
        )
        self._show_debug(f"Archivo: {pdf_path} movido a la posicion con index {new_index}")
        self._refresh_merge_file_widgets()

    def _remove_merge_file(self, pdf_path: Path) -> None:
        if pdf_path not in self.pdf_files:
            return
        self.pdf_files.remove(pdf_path)
        self._refresh_merge_file_widgets()
        self._show_debug(f"Archivo: {pdf_path} eliminado de la lista de pdfs por unificar")

    def _clear_merge_files(self) -> None:
        for widget in self.file_widgets.values():
            widget.destroy()
        self.pdf_files.clear()
        self.file_widgets.clear()
        self._show_debug(f"Lista de archivos pdfs por unir reiniciada")

    def _select_merge_output(self) -> None:
        output_file = self._ask_pdf_save_path("Guardar PDF unificado")
        if output_file:
            self.merge_output_entry.delete(0, "end")
            self.merge_output_entry.insert(0, str(output_file))

    def _merge_pdf_files(self) -> None:
        try:
            if not self.pdf_files:
                raise ValueError("Debe agregar al menos un archivo PDF.")
            output_file = self.merge_output_entry.get().strip()
            pdf_files = tuple(self.pdf_files)
            self._run_background_task(
                "Uniendo PDFs",
                "PDF unificado",
                lambda: TheManipulation.concatenate_pdf_files(
                    pdf_files,
                    output_file,
                ),
            )
        except Exception as error:
            self._show_error(error)

    def _select_split_pdf(self) -> None:
        file_name = self._ask_pdf_open_path("Seleccionar PDF a desunir")
        if not file_name:
            return

        self.split_pdf_file.set(str(file_name))
        self.split_output_file.set(
            str(paths.path_to_export / f"{file_name.stem}_paginas.pdf")
        )
        self._update_split_page_count(file_name)

    def _select_split_output(self) -> None:
        output_file = self._ask_pdf_save_path("Guardar PDF extraido")
        if output_file:
            self.split_output_file.set(str(output_file))

    def _update_split_page_count(self, pdf_file: Path) -> None:
        try:
            with fitz.open(pdf_file) as document:
                self.split_page_count.set(f"El PDF tiene {document.page_count} paginas.")
        except Exception:
            self.split_page_count.set("No se pudo leer el numero de paginas.")

    def _split_pdf_file(self) -> None:
        password = self.split_password.get().strip() or None
        self._start_split_task(password)

    def _start_split_task(self, password: str | None) -> None:
        input_pdf = self.split_pdf_file.get().strip()
        output_pdf = self.split_output_file.get().strip()
        page_selection = self.split_pages.get().strip()
        output_password = self.split_output_password.get().strip() or None

        self._run_background_task(
            "Extrayendo paginas",
            "PDF dividido",
            lambda: TheManipulation.extract_pdf_pages(
                input_pdf=input_pdf,
                output_pdf=output_pdf,
                page_selection=page_selection,
                password=password,
                output_password=output_password,
            ),
            on_error=lambda error: self._handle_split_error(error, password),
        )

    def _handle_split_error(self, error: Exception, password: str | None) -> None:
        if "protegido" not in str(error).lower() or password:
            self._show_error(error)
            return

        password = simpledialog.askstring(
            "Contraseña requerida",
            "El PDF origen esta protegido. Ingrese la contraseña:",
            show="*",
            parent=self.root,
        )
        if password:
            self.split_password.set(password)
            self._start_split_task(password)

    def _select_office_file(self) -> None:
        file_name = filedialog.askopenfilename(
            title="Seleccionar archivo Office",
            filetypes=(
                ("Archivos Office", "*.docx *.xlsx"),
                ("Word", "*.docx"),
                ("Excel", "*.xlsx"),
            ),
        )
        if file_name:
            self.office_file.set(file_name)
            self.office_output.set(
                str(paths.path_to_export / f"{Path(file_name).stem}.pdf")
            )

    def _select_office_output(self) -> None:
        output_file = self._ask_pdf_save_path("Guardar PDF convertido")
        if output_file:
            self.office_output.set(str(output_file))

    def _convert_office_file(self) -> None:
        try:
            origin_file = self.office_file.get().strip()
            output_file = self.office_output.get().strip()
            self._run_background_task(
                "Convirtiendo archivo",
                "Archivo transformado a PDF",
                lambda: TheManipulation.transform_office_2_pdf(
                    origin_file,
                    output_file,
                ),
            )
        except Exception as error:
            self._show_error(error)

    def _select_sign_pdf(self) -> None:
        file_name = self._ask_pdf_open_path("Seleccionar PDF a firmar")
        if file_name:
            self.sign_pdf_file.set(str(file_name))
            self.sign_output_file.set(
                str(paths.path_to_export / f"{file_name.stem}_firmado.pdf")
            )
            self.sign_preview_page_index = 0
            self.signature_page.set("0")
            self._render_sign_preview()

    def _select_sign_output(self) -> None:
        output_file = self._ask_pdf_save_path("Guardar PDF firmado")
        if output_file:
            self.sign_output_file.set(str(output_file))

    def _select_signature_image(self) -> None:
        file_name = filedialog.askopenfilename(
            title="Seleccionar imagen de firma",
            filetypes=(
                ("Imagenes", "*.png *.jpg *.jpeg"),
                ("PNG", "*.png"),
                ("JPG", "*.jpg *.jpeg"),
            ),
        )
        if file_name:
            output_path = self._store_signature_image(Path(file_name))
            self._refresh_signature_list(selected_path=output_path)

    def _store_signature_image(self, source_path: Path, signature_name: str | None = None) -> Path:
        paths.path_to_signs.mkdir(parents=True, exist_ok=True)

        if signature_name:
            clean_name = self._clean_file_name(signature_name)
            output_path = paths.path_to_signs / f"{clean_name}{source_path.suffix.lower()}"
        else:
            output_path = paths.path_to_signs / source_path.name

        if output_path.exists() and source_path.resolve() != output_path.resolve():
            output_path = output_path.with_stem(
                f"{output_path.stem}_{datetime.now().strftime('%H%M%S')}"
            )

        if source_path.resolve() != output_path.resolve():
            shutil.copy2(source_path, output_path)

        return output_path

    def _refresh_signature_list(self, selected_path: Path | None = None) -> None:
        paths.path_to_signs.mkdir(parents=True, exist_ok=True)
        signature_files = sorted(
            file_path
            for file_path in paths.path_to_signs.iterdir()
            if file_path.suffix.lower() in (".png", ".jpg", ".jpeg")
        )

        self.signature_image_paths = {
            signature_file.name: signature_file for signature_file in signature_files
        }
        values = ["Sin imagen", *self.signature_image_paths.keys()]

        if hasattr(self, "signature_image_combo"):
            self.signature_image_combo.configure(values=values)

        if selected_path:
            selected_name = selected_path.name
            self.signature_image_label.set(selected_name)
            self.signature_image.set(str(selected_path))
            return

        current_path = Path(self.signature_image.get()) if self.signature_image.get() else None
        if current_path and current_path.name in self.signature_image_paths:
            self.signature_image_label.set(current_path.name)
        else:
            self.signature_image_label.set("Sin imagen")
            self.signature_image.set("")

    def _select_saved_signature(self, signature_name: str) -> None:
        if signature_name == "Sin imagen":
            self.signature_image_label.set("Sin imagen")
            self.signature_image.set("")
            return

        signature_path = self.signature_image_paths.get(signature_name)
        if signature_path:
            self.signature_image.set(str(signature_path))
            self.signature_image_label.set(signature_name)

    def _delete_selected_signature(self) -> None:
        signature_name = self.signature_image_label.get()
        signature_path = self.signature_image_paths.get(signature_name)
        if not signature_path:
            messagebox.showinfo("Firma", "Seleccione una firma guardada para borrar.")
            return

        delete_signature = messagebox.askyesno(
            "Borrar firma",
            f"Desea borrar la firma '{signature_name}'?",
        )
        if not delete_signature:
            return

        signature_path.unlink()
        self.signature_image.set("")
        self.signature_image_label.set("Sin imagen")
        self._refresh_signature_list()

    def _on_signature_image_changed(self, *_args) -> None:
        self._update_signature_preview()
        if hasattr(self, "sign_preview_canvas"):
            self._draw_signature_marker()

    def _update_signature_preview(self) -> None:
        if not hasattr(self, "signature_preview_label"):
            return

        signature_file = self.signature_image.get().strip()
        if not signature_file:
            self.signature_source_image = None
            self.signature_preview_image = None
            self.signature_preview_label.configure(image=None, text="Vista previa")
            return

        try:
            image = Image.open(signature_file).convert("RGBA")
            image.thumbnail((250, 95))
            self.signature_source_image = image.copy()
            self.signature_preview_image = ctk.CTkImage(
                light_image=image,
                dark_image=image,
                size=image.size,
            )
            self.signature_preview_label.configure(
                image=self.signature_preview_image,
                text="",
            )
        except Exception:
            self.signature_source_image = None
            self.signature_preview_image = None
            self.signature_preview_label.configure(image=None, text="No se pudo cargar")

    @staticmethod
    def _clean_file_name(file_name: str) -> str:
        clean_name = file_name.strip() or "firma"
        clean_name = "".join(
            character
            for character in clean_name
            if character.isalnum() or character in ("_", "-")
        )
        return clean_name or "firma"

    def _change_sign_preview_page(self, offset: int) -> None:
        if not self.sign_pdf_file.get().strip():
            return

        new_page_index = self.sign_preview_page_index + offset
        if new_page_index < 0 or new_page_index >= self.sign_preview_page_count:
            return

        self.sign_preview_page_index = new_page_index
        self.signature_page.set(str(new_page_index))
        self._render_sign_preview()

    def _go_to_sign_preview_page(self, page_index: int) -> None:
        if not self.sign_pdf_file.get().strip():
            return
        if page_index < 0 or page_index >= self.sign_preview_page_count:
            return

        self.sign_preview_page_index = page_index
        self.signature_page.set(str(page_index))
        self._render_sign_preview()

    def _go_to_last_sign_preview_page(self) -> None:
        self._go_to_sign_preview_page(self.sign_preview_page_count - 1)

    def _change_sign_preview_zoom(self, zoom_delta: float) -> None:
        if not self.sign_pdf_file.get().strip():
            return

        self.sign_preview_zoom = max(
            0.5,
            min(self.sign_preview_zoom + zoom_delta, 4.0),
        )
        self._render_sign_preview()

    def _reset_sign_preview_zoom(self) -> None:
        self.sign_preview_zoom = 1.0
        self._render_sign_preview()

    def _render_sign_preview(self) -> None:
        pdf_file = self.sign_pdf_file.get().strip()
        if not pdf_file:
            return

        try:
            self.sign_preview_canvas.update_idletasks()
            canvas_width = max(self.sign_preview_canvas.winfo_width(), 640)
            canvas_height = max(self.sign_preview_canvas.winfo_height(), 480)

            with fitz.open(pdf_file) as document:
                self.sign_preview_page_count = document.page_count
                page = document[self.sign_preview_page_index]
                page_rect = page.rect
                self.sign_preview_page_origin = (page_rect.x0, page_rect.y0)
                self.sign_preview_scale = min(
                    canvas_width / page_rect.width,
                    canvas_height / page_rect.height,
                )
                self.sign_preview_scale = max(self.sign_preview_scale, 0.1)
                self.sign_preview_scale *= self.sign_preview_zoom

                matrix = fitz.Matrix(self.sign_preview_scale, self.sign_preview_scale)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                image = Image.frombytes(
                    "RGB",
                    [pixmap.width, pixmap.height],
                    pixmap.samples,
                )

            self.sign_preview_image = ImageTk.PhotoImage(image)
            self.sign_preview_canvas.delete("all")
            self.sign_preview_canvas.config(
                scrollregion=(0, 0, image.width, image.height),
            )
            self.sign_preview_canvas.create_image(
                0,
                0,
                anchor="nw",
                image=self.sign_preview_image,
            )
            self.sign_page_label.configure(
                text=f"Pagina {self.sign_preview_page_index + 1} de {self.sign_preview_page_count}"
            )
            self.sign_zoom_label.configure(text=f"{self.sign_preview_zoom:.0%}")
            self._draw_signature_marker()
        except Exception as error:
            self._show_error(error)

    def _set_signature_location_from_preview(self, event: tk.Event) -> None:
        if not self.sign_pdf_file.get().strip():
            return

        canvas_x = self.sign_preview_canvas.canvasx(event.x)
        canvas_y = self.sign_preview_canvas.canvasy(event.y)
        origin_x, origin_y = self.sign_preview_page_origin
        x_coordinate = (canvas_x / self.sign_preview_scale) + origin_x
        y_coordinate = (canvas_y / self.sign_preview_scale) + origin_y

        self.signature_x.set(f"{x_coordinate:.2f}")
        self.signature_y.set(f"{y_coordinate:.2f}")
        self.signature_page.set(str(self.sign_preview_page_index))
        self._draw_signature_marker(canvas_x, canvas_y)

    def _draw_signature_marker(
        self,
        x_coordinate: float | None = None,
        y_coordinate: float | None = None,
    ) -> None:
        self.sign_preview_canvas.delete("signature_marker")

        if x_coordinate is None or y_coordinate is None:
            try:
                origin_x, origin_y = self.sign_preview_page_origin
                x_coordinate = (
                    float(self.signature_x.get()) - origin_x
                ) * self.sign_preview_scale
                y_coordinate = (
                    float(self.signature_y.get()) - origin_y
                ) * self.sign_preview_scale
            except ValueError:
                return

        marker_size = 8
        signature_file = self.signature_image.get().strip()
        if signature_file:
            try:
                preview_width = max(1, int(180 * self.sign_preview_scale))
                preview_height = max(1, int(80 * self.sign_preview_scale))
                source_image = self.signature_source_image
                if source_image is None:
                    source_image = Image.open(signature_file).convert("RGBA")
                preview_image = source_image.resize((preview_width, preview_height))
                self.sign_overlay_image = ImageTk.PhotoImage(preview_image)
                self.sign_preview_canvas.create_image(
                    x_coordinate,
                    y_coordinate,
                    anchor="nw",
                    image=self.sign_overlay_image,
                    tags="signature_marker",
                )
                return
            except Exception:
                self.sign_overlay_image = None

        self.sign_preview_canvas.create_line(
            x_coordinate - marker_size,
            y_coordinate,
            x_coordinate + marker_size,
            y_coordinate,
            fill="#e53935",
            width=2,
            tags="signature_marker",
        )
        self.sign_preview_canvas.create_line(
            x_coordinate,
            y_coordinate - marker_size,
            x_coordinate,
            y_coordinate + marker_size,
            fill="#e53935",
            width=2,
            tags="signature_marker",
        )

    def _open_signature_window(self) -> None:
        paths.path_to_signs.mkdir(parents=True, exist_ok=True)

        signature_window = ctk.CTkToplevel(self.root)
        if PENCIL_ICON.exists():
            signature_window.iconbitmap(str(PENCIL_ICON))
        signature_window.title("Crear firma")
        signature_window.geometry("640x420")
        signature_window.resizable(False, False)

        signature_name = tk.StringVar(
            value=f"firma_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        strokes: list[list[tuple[int, int]]] = []
        current_stroke: list[tuple[int, int]] = []

        form = ctk.CTkFrame(signature_window, corner_radius=8)
        form.pack(fill="x", padx=12, pady=(12, 8))
        form.grid_columnconfigure(1, weight=1)

        name_label = ctk.CTkLabel(form, text="Nombre")
        name_label.grid(row=0, column=0, sticky="w", padx=10, pady=8)

        name_entry = ctk.CTkEntry(form, textvariable=signature_name)
        name_entry.grid(row=0, column=1, sticky="ew", padx=10, pady=8)

        drawing_canvas = tk.Canvas(
            signature_window,
            width=600,
            height=240,
            background="white",
            highlightthickness=1,
            highlightbackground="#444444",
        )
        drawing_canvas.pack(padx=12, pady=8)

        def start_draw(event: tk.Event) -> None:
            current_stroke.clear()
            current_stroke.append((event.x, event.y))

        def draw(event: tk.Event) -> None:
            if not current_stroke:
                return
            last_x, last_y = current_stroke[-1]
            drawing_canvas.create_line(
                last_x,
                last_y,
                event.x,
                event.y,
                width=3,
                fill="black",
                capstyle="round",
                smooth=True,
            )
            current_stroke.append((event.x, event.y))

        def end_draw(event: tk.Event) -> None:
            del event
            if current_stroke:
                strokes.append(current_stroke.copy())
                current_stroke.clear()

        def clear_signature() -> None:
            strokes.clear()
            current_stroke.clear()
            drawing_canvas.delete("all")

        def signature_output_path(extension: str = ".png") -> Path:
            clean_name = self._clean_file_name(signature_name.get())
            return paths.path_to_signs / f"{clean_name}{extension}"

        def save_signature() -> None:
            if not strokes:
                messagebox.showwarning("Firma vacia", "Dibuja una firma antes de guardarla.")
                return

            output_path = signature_output_path()
            signature_image = Image.new("RGBA", (600, 240), (255, 255, 255, 0))
            image_draw = ImageDraw.Draw(signature_image)
            for stroke in strokes:
                if len(stroke) > 1:
                    image_draw.line(stroke, fill=(0, 0, 0, 255), width=3, joint="curve")

            signature_image.save(output_path)
            self._refresh_signature_list(selected_path=output_path)
            signature_window.destroy()

        def import_signature() -> None:
            file_name = filedialog.askopenfilename(
                title="Adjuntar firma desde imagen",
                filetypes=(
                    ("Imagenes", "*.png *.jpg *.jpeg"),
                    ("PNG", "*.png"),
                    ("JPG", "*.jpg *.jpeg"),
                ),
            )
            if not file_name:
                return

            source_path = Path(file_name)
            output_path = self._store_signature_image(
                source_path,
                signature_name=signature_name.get(),
            )
            self._refresh_signature_list(selected_path=output_path)
            signature_window.destroy()

        drawing_canvas.bind("<ButtonPress-1>", start_draw)
        drawing_canvas.bind("<B1-Motion>", draw)
        drawing_canvas.bind("<ButtonRelease-1>", end_draw)

        buttons = ctk.CTkFrame(signature_window, fg_color="transparent")
        buttons.pack(fill="x", padx=12, pady=10)

        clear_button = ctk.CTkButton(
            buttons,
            text="Limpiar",
            fg_color="transparent",
            border_width=1,
            command=clear_signature,
        )
        clear_button.pack(side="left", padx=6)

        import_button = ctk.CTkButton(
            buttons,
            text="Adjuntar imagen",
            command=import_signature,
        )
        import_button.pack(side="right", padx=6)

        save_button = ctk.CTkButton(
            buttons,
            text="Guardar firma",
            command=save_signature,
        )
        save_button.pack(side="right", padx=6)

    def _sign_pdf(self) -> None:
        try:
            signature_image = self.signature_image.get().strip() or None
            if not signature_image:
                raise ValueError("Debe seleccionar una imagen de firma.")

            page_number = int(self.signature_page.get().strip())
            signature_location = (
                float(self.signature_x.get().strip()),
                float(self.signature_y.get().strip()),
            )

            input_pdf = self.sign_pdf_file.get().strip()
            output_pdf = self.sign_output_file.get().strip()
            sign_all_pages = self.sign_all_pages.get()
            self._run_background_task(
                "Firmando PDF",
                "PDF firmado",
                lambda: TheManipulation.sign_pdf(
                    input_pdf=input_pdf,
                    output_pdf=output_pdf,
                    signature_image=signature_image,
                    signature_location=signature_location,
                    page_number=page_number,
                    sign_all_pages=sign_all_pages,
                ),
            )
        except Exception as error:
            self._show_error(error)

    def _select_security_pdf(self) -> None:
        file_name = self._ask_pdf_open_path("Seleccionar PDF")
        if file_name:
            self.security_pdf_file.set(str(file_name))
            self._set_default_security_output()

    def _select_security_output(self) -> None:
        output_file = self._ask_pdf_save_path("Guardar PDF")
        if output_file:
            self.security_output_file.set(str(output_file))

    def _set_default_security_output(self) -> None:
        input_file = self.security_pdf_file.get().strip()
        if not input_file:
            return

        input_path = Path(input_file)
        suffix = "bloqueado" if self.security_mode.get() == "Bloquear" else "libre"
        output_path = paths.path_to_export / f"{input_path.stem}_{suffix}.pdf"
        self.security_output_file.set(str(output_path))

    def _run_security_action(self) -> None:
        try:
            input_file = self.security_pdf_file.get().strip()
            output_file = self.security_output_file.get().strip()
            password = self.security_password.get()

            if self.security_mode.get() == "Bloquear":
                task = lambda: TheManipulation.lock_pdf(input_file, output_file, password)
            else:
                task = lambda: TheManipulation.unlock_pdf(input_file, output_file, password)

            self._run_background_task("Procesando seguridad", "PDF procesado", task)
        except Exception as error:
            self._show_error(error)

    def _save_settings(
        self,
        width: str,
        height: str,
        theme: str,
        color_theme: str,
        initial_tab: str,
        ui_scaling: str,
        open_after_save: str,
    ) -> None:
        try:
            int(width)
            int(height)
            scaling_value = self._scaling_label_to_value(ui_scaling)
            if scaling_value < 0.5 or scaling_value > 2.0:
                raise ValueError("La escala UI debe estar entre 0.5 y 2.0.")

            config = utils.configparser.ConfigParser()
            config.read(APP_DEFAULT_SETTINGS_FILE, encoding="utf-8")
            config["Size"]["width"] = width
            config["Size"]["height"] = height
            config["Theme"]["theme"] = theme
            config["Theme"]["color_theme"] = color_theme
            if "Display" not in config:
                config["Display"] = {}
            config["Display"]["ui_scaling"] = str(scaling_value)
            config["Display"]["open_after_save"] = (
                "yes" if open_after_save.strip().lower() in ("si", "sí", "yes") else "no"
            )
            self.open_after_save.set(
                "Si" if open_after_save.strip().lower() in ("si", "sí", "yes") else "No"
            )
            config["App"]["initial_window"] = initial_tab

            with APP_DEFAULT_SETTINGS_FILE.open("w", encoding="utf-8") as config_file:
                config.write(config_file)

            restart_now = messagebox.askyesno(
                "Configuracion guardada",
                "Para tomar los cambios se necesita reiniciar la aplicacion.\n\n"
                "Desea reiniciar ahora?",
            )
            if restart_now:
                self._restart_app()
        except Exception as error:
            self._show_error(error)

    @staticmethod
    def _scaling_to_label(scaling_value: float) -> str:
        return f"{int(round(scaling_value * 100))}%"

    @staticmethod
    def _scaling_label_to_value(scaling_label: str) -> float:
        clean_label = scaling_label.strip().replace("%", "")
        return float(clean_label) / 100

    def _open_help_window(self) -> None:
        help_window = ctk.CTkToplevel(self.root)
        if HELP_ICON.exists():
            help_window.iconbitmap(str(HELP_ICON))
        help_window.title("Ayuda de uso")
        help_window.geometry("860x620")
        help_window.minsize(720, 480)

        text_box = ctk.CTkTextbox(help_window, wrap="word")
        text_box.pack(fill="both", expand=True, padx=14, pady=14)

        if USER_GUIDE_FILE.exists():
            help_text = USER_GUIDE_FILE.read_text(encoding="utf-8")
        else:
            help_text = "No se encontro la documentacion de uso."

        self._insert_markdown_help(text_box, help_text)
        text_box.configure(state="disabled")

    def _insert_markdown_help(self, text_box: ctk.CTkTextbox, markdown_text: str) -> None:
        native_text_box = text_box._textbox
        native_text_box.tag_configure("h1", font=("Segoe UI", 22, "bold"), spacing3=12)
        native_text_box.tag_configure(
            "h2",
            font=("Segoe UI", 17, "bold"),
            spacing1=10,
            spacing3=6,
        )
        native_text_box.tag_configure("body", font=("Segoe UI", 11), spacing3=4)
        native_text_box.tag_configure(
            "list",
            font=("Segoe UI", 11),
            lmargin1=22,
            lmargin2=38,
            spacing3=3,
        )
        native_text_box.tag_configure(
            "code",
            font=("Consolas", 10),
            background="#eeeeee",
        )

        for line in markdown_text.splitlines():
            clean_line = line.strip()
            clean_line = clean_line.replace("**", "").replace("`", "")
            if clean_line.startswith("# "):
                native_text_box.insert("end", f"{clean_line[2:]}\n", "h1")
            elif clean_line.startswith("## "):
                native_text_box.insert("end", f"\n{clean_line[3:]}\n", "h2")
            elif clean_line.startswith("- "):
                native_text_box.insert("end", f"  • {clean_line[2:]}\n", "list")
            elif clean_line and clean_line[0].isdigit() and ". " in clean_line[:4]:
                native_text_box.insert("end", f"{clean_line}\n", "list")
            elif clean_line.startswith("```"):
                continue
            elif clean_line:
                native_text_box.insert("end", f"{clean_line}\n", "body")
            else:
                native_text_box.insert("end", "\n", "body")

    def _toggle_theme(self) -> None:
        next_theme = "Light" if str(self.current_theme.get()).lower() == "dark" else "Dark"
        self.current_theme.set(next_theme)
        ctk.set_appearance_mode(next_theme)
        self.theme_switch.configure(text=next_theme)

    def _change_ui_scaling(self, scaling_delta: float) -> None:
        next_scaling = max(
            0.75,
            min(self.current_scaling.get() + scaling_delta, 1.5),
        )
        next_scaling = round(next_scaling, 2)
        self.current_scaling.set(next_scaling)
        self.scaling_label.set(f"{int(next_scaling * 100)}%")
        ctk.set_widget_scaling(next_scaling)

    def _run_background_task(
        self,
        description: str,
        success_title: str,
        task: Callable[[], Path],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Ejecuta una operacion de archivo sin bloquear la interfaz."""
        self.pending_task_count += 1
        self.status_message.set(f"{description}...")
        self.activity_progress.start()
        future = self.task_executor.submit(task)
        future.add_done_callback(
            lambda completed: self._schedule_task_completion(
                completed,
                success_title,
                on_error,
            )
        )

    def _schedule_task_completion(
        self,
        future: Future[Path],
        success_title: str,
        on_error: Callable[[Exception], None] | None,
    ) -> None:
        try:
            self.root.after(
                0,
                self._complete_background_task,
                future,
                success_title,
                on_error,
            )
        except tk.TclError:
            return

    def _complete_background_task(
        self,
        future: Future[Path],
        success_title: str,
        on_error: Callable[[Exception], None] | None,
    ) -> None:
        self.pending_task_count = max(0, self.pending_task_count - 1)
        if not self.pending_task_count:
            self.activity_progress.stop()
            self.activity_progress.set(0)
            self.status_message.set("Listo para procesar archivos")

        try:
            result = future.result()
        except Exception as error:
            if on_error:
                on_error(error)
            else:
                self._show_error(error)
            return

        self._show_success(success_title, result)

    def _restart_app(self) -> None:
        self.task_executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()
        os.execl(sys.executable, sys.executable, *sys.argv)

    def _exit_program(self) -> None:
        self.task_executor.shutdown(wait=False, cancel_futures=True)
        self.root.destroy()
        sys.exit(0)

    def _content_frame(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent, corner_radius=8)
        frame.pack(fill="both", expand=True, padx=8, pady=8)
        return frame

    def _form_frame(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        form = ctk.CTkFrame(parent, corner_radius=8)
        form.pack(fill="x", padx=16, pady=12)
        form.grid_columnconfigure(1, weight=1)
        return form

    def _title(self, parent: ctk.CTkFrame, text: str) -> None:
        title = ctk.CTkLabel(parent, text=text, font=("Segoe UI", 20, "bold"))
        title.pack(anchor="w", padx=16, pady=(14, 4))

    def _file_row(
        self,
        parent: ctk.CTkFrame,
        row: int,
        label: str,
        variable: tk.StringVar,
        command,
    ) -> None:
        row_label = ctk.CTkLabel(parent, text=label)
        row_label.grid(row=row, column=0, sticky="w", padx=10, pady=8)

        entry = ctk.CTkEntry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", padx=10, pady=8)

        button = ctk.CTkButton(parent, text="Seleccionar", width=110, command=command)
        button.grid(row=row, column=2, padx=10, pady=8)

    def _signature_image_row(self, parent: ctk.CTkFrame, row: int) -> None:
        row_label = ctk.CTkLabel(parent, text="Imagen de firma")
        row_label.grid(row=row, column=0, sticky="w", padx=10, pady=8)

        self.signature_image_combo = ctk.CTkComboBox(
            parent,
            values=["Sin imagen"],
            variable=self.signature_image_label,
            command=self._select_saved_signature,
            state="readonly",
        )
        self.signature_image_combo.grid(row=row, column=1, sticky="ew", padx=10, pady=8)

        attach_button = ctk.CTkButton(
            parent,
            text="Adjuntar",
            width=82,
            command=self._select_signature_image,
        )
        attach_button.grid(row=row, column=2, padx=10, pady=8)

        delete_button = ctk.CTkButton(
            parent,
            text="Borrar",
            width=74,
            fg_color="transparent",
            border_width=1,
            command=self._delete_selected_signature,
        )
        delete_button.grid(row=row, column=3, padx=(0, 10), pady=8)
        self._refresh_signature_list()

    def _entry_row(
        self,
        parent: ctk.CTkFrame,
        row: int,
        label: str,
        variable: tk.StringVar,
        show: str | None = None,
    ) -> None:
        row_label = ctk.CTkLabel(parent, text=label)
        row_label.grid(row=row, column=0, sticky="w", padx=10, pady=8)

        entry = ctk.CTkEntry(parent, textvariable=variable, show=show)
        entry.grid(row=row, column=1, columnspan=2, sticky="ew", padx=10, pady=8)

    def _combo_row(
        self,
        parent: ctk.CTkFrame,
        row: int,
        label: str,
        variable: tk.StringVar,
        values: list[str]
    ) -> None:
        row_label = ctk.CTkLabel(parent, text=label)
        row_label.grid(row=row, column=0, sticky="w", padx=10, pady=8)

        combo = ctk.CTkComboBox(parent, values=values, variable=variable, width=170)
        combo.grid(row=row, column=1, sticky="w", padx=10, pady=8)

    def _small_entry(
        self,
        parent: ctk.CTkFrame,
        label: str,
        variable: tk.StringVar,
        column: int,
    ) -> None:
        group = ctk.CTkFrame(parent, fg_color="transparent")
        group.grid(row=0, column=column, sticky="ew", padx=4)
        group.grid_columnconfigure(1, weight=1)

        row_label = ctk.CTkLabel(group, text=label)
        row_label.grid(row=0, column=0, padx=(0, 6))

        entry = ctk.CTkEntry(group, textvariable=variable)
        entry.grid(row=0, column=1, sticky="ew")

    def _path_entry(
        self,
        parent: ctk.CTkFrame,
        placeholder: str,
        initial_value: Path,
        command,
    ) -> ctk.CTkEntry:
        container = ctk.CTkFrame(parent, fg_color="transparent")
        container.pack(side="left", fill="x", expand=True, padx=8)
        container.grid_columnconfigure(0, weight=1)

        entry = ctk.CTkEntry(container, placeholder_text=placeholder)
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 8), pady=10)
        entry.insert(0, str(initial_value))

        button = ctk.CTkButton(container, text="Destino", width=90, command=command)
        button.grid(row=0, column=1, pady=10)
        return entry

    def _ask_pdf_open_path(self, title: str) -> Path | None:
        file_name = filedialog.askopenfilename(
            title=title,
            filetypes=(("Archivos PDF", "*.pdf"),),
        )
        return Path(file_name) if file_name else None

    def _ask_pdf_save_path(self, title: str) -> Path | None:
        file_name = filedialog.asksaveasfilename(
            title=title,
            defaultextension=".pdf",
            initialdir=paths.path_to_export,
            filetypes=(("Archivos PDF", "*.pdf"),),
        )
        return Path(file_name) if file_name else None

    def _show_success(self, title: str, file_path: Path) -> None:
        logger_user.info(f"{title}: {file_path}")
        messagebox.showinfo(title, f"Archivo generado:\n{file_path}")
        if self.open_after_save.get() == "Si":
            self._open_output_file(file_path)

    def _open_output_file(self, file_path: Path | str) -> None:
        output_path = Path(file_path)
        if not output_path.exists():
            return
        try:
            os.startfile(output_path)
        except OSError as error:
            logger_dev.error(f"No se pudo abrir el archivo generado: {error}")

    def _show_debug(self, title: str) -> None:
        logger_user.debug(f"{title}")

    def _show_error(self, error: Exception) -> None:
        logger_dev.error(error)
        messagebox.showerror("Error", str(error))

    def _load_image(self, image_path: Path) -> ctk.CTkImage | None:
        if not image_path.exists():
            return None
        image = Image.open(image_path)
        return ctk.CTkImage(image, size=(18, 18))

    @staticmethod
    def _center_window(window: tk.Tk | ctk.CTkToplevel, width: int, height: int) -> None:
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        x_position = (screen_width // 2) - (width // 2)
        y_position = (screen_height // 2) - (height // 2)
        window.geometry(f"{width}x{height}+{x_position}+{y_position}")


class TheGui(PdfManagementGui):
    """
    Alias compatible con el nombre usado por utils.TheExecution.
    """


class ToolTip:
    """
    Tooltip simple para widgets de CustomTkinter.
    """

    def __init__(self, widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tip_window = None
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None) -> None:
        if self.tip_window or not self.text:
            return

        x_position = self.widget.winfo_rootx() + 25
        y_position = self.widget.winfo_rooty() + 20
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{x_position}+{y_position}")

        label = tk.Label(
            self.tip_window,
            text=self.text,
            justify="left",
            background="#ffffe0",
            relief="solid",
            borderwidth=1,
            font=("Segoe UI", 9),
        )
        label.pack(ipadx=5, ipady=3)

    def hide_tip(self, event=None) -> None:
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


if __name__ == "__main__":
    pass
