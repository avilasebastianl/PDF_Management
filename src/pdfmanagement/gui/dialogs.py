"""
Ventanas secundarias: contrasena, ayuda y creacion de firmas.
"""

import tkinter as tk
from tkinter import messagebox
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageDraw

from .. import paths
from ..signatures import signature_path_for
from . import style
from .events import debug_event
from .widgets import primary_button, secondary_button


def _prepare_toplevel(window: ctk.CTkToplevel, parent, title: str, width: int, height: int, modal: bool) -> None:
    window.title(title)
    window.transient(parent.winfo_toplevel())
    if paths.APP_ICON.exists():
        window.after(250, lambda: window.iconbitmap(str(paths.APP_ICON)))
    parent.update_idletasks()
    root = parent.winfo_toplevel()
    x = root.winfo_rootx() + (root.winfo_width() - width) // 2
    y = root.winfo_rooty() + (root.winfo_height() - height) // 3
    window.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")
    if modal:
        window.after(50, window.grab_set)
    window.bind("<Escape>", lambda _event: window.destroy())


# * Contrasena --------------------------------------------------------------

def ask_password(parent, file_name: str, retry: bool = False) -> str | None:
    """Solicita la contrasena de un PDF en un dialogo modal. ``None`` si se cancela."""
    message = (
        f"La contrasena de '{file_name}' no es correcta. Intente de nuevo:"
        if retry
        else f"'{file_name}' esta protegido. Ingrese su contrasena:"
    )
    return _password_dialog(parent, "Contrasena requerida", message) or None


def ask_certificate_password(parent, file_name: str, retry: bool = False) -> str | None:
    """
    Solicita la contrasena del certificado .pfx/.p12. Devuelve ``None`` si se
    cancela y ``""`` si se acepta vacia (certificados sin contrasena). Nunca se
    guarda: solo vive en memoria durante la firma.
    """
    message = (
        f"La contrasena del certificado '{file_name}' no es correcta. Intente de nuevo:"
        if retry
        else f"Ingrese la contrasena del certificado '{file_name}'.\nNo se guarda en ningun lugar."
    )
    return _password_dialog(parent, "Contrasena del certificado", message)


def _password_dialog(parent, title: str, message: str) -> str | None:
    window = ctk.CTkToplevel(parent)
    _prepare_toplevel(window, parent, title, 420, 220, modal=True)
    window.resizable(False, False)
    result: dict[str, str | None] = {"value": None}

    ctk.CTkLabel(window, text=message, font=style.fonts().body, wraplength=380, justify="left").pack(
        fill="x", padx=20, pady=(20, 10)
    )
    entry = ctk.CTkEntry(window, show="•", height=36)
    entry.pack(fill="x", padx=20)

    def accept(_event=None) -> None:
        result["value"] = entry.get()
        window.destroy()

    buttons = ctk.CTkFrame(window, fg_color="transparent")
    buttons.pack(fill="x", padx=20, pady=20)
    primary_button(buttons, "Aceptar", accept, width=110).pack(side="right")
    secondary_button(buttons, "Cancelar", window.destroy, width=110).pack(side="right", padx=8)
    entry.bind("<Return>", accept)
    window.after(100, entry.focus_force)
    parent.wait_window(window)
    return result["value"]


# * Propiedades del documento -----------------------------------------------

class DocumentPropertiesWindow(ctk.CTkToplevel):
    """Datos del PDF abierto en el visor (solo lectura)."""

    def __init__(self, parent, properties, current_page_size: tuple[float, float] | None = None) -> None:
        super().__init__(parent)
        _prepare_toplevel(self, parent, "Propiedades del documento", 520, 520, modal=False)
        self.resizable(False, False)
        frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        frame.grid_columnconfigure(1, weight=1)

        def size_text(size_bytes: int) -> str:
            value = float(size_bytes)
            for unit in ("B", "KB", "MB"):
                if value < 1024:
                    return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
                value /= 1024
            return f"{value:.1f} GB"

        rows = [
            ("Archivo", properties.path.name),
            ("Carpeta", str(properties.path.parent)),
            ("Tamano", size_text(properties.size_bytes)),
            ("Paginas", str(properties.page_count)),
        ]
        if current_page_size:
            width, height = current_page_size
            rows.append(("Pagina actual", f"{width:.0f} x {height:.0f} pt  ({width / 72 * 25.4:.0f} x {height / 72 * 25.4:.0f} mm)"))
        rows += [
            ("Version PDF", properties.pdf_version or "-"),
            ("Protegido", "Si, con contrasena" if properties.encrypted else "No"),
            ("Firmas digitales", "Si (editarlo invalidaria las firmas)" if properties.has_signatures else "No"),
            ("Titulo", properties.title or "-"),
            ("Autor", properties.author or "-"),
            ("Asunto", properties.subject or "-"),
            ("Palabras clave", properties.keywords or "-"),
            ("Creado con", properties.creator or "-"),
            ("Producido por", properties.producer or "-"),
            ("Creado", properties.created or "-"),
            ("Modificado", properties.modified or "-"),
        ]
        for row, (label, value) in enumerate(rows):
            ctk.CTkLabel(frame, text=label, font=style.fonts().body_bold, anchor="nw").grid(
                row=row, column=0, sticky="nw", padx=(4, 14), pady=3
            )
            ctk.CTkLabel(frame, text=value, font=style.fonts().body, anchor="w", justify="left", wraplength=320).grid(
                row=row, column=1, sticky="w", pady=3
            )
        primary_button(self, "Cerrar", self.destroy, width=110).pack(anchor="e", padx=16, pady=(0, 14))


# * Ayuda -------------------------------------------------------------------

class HelpWindow(ctk.CTkToplevel):
    """
    Muestra ``docs/user_guide.md`` con un formato Markdown basico, un indice
    lateral de secciones y bloques de codigo con boton "Copiar".
    """

    def __init__(self, parent, section: str | None = None) -> None:
        super().__init__(parent)
        _prepare_toplevel(self, parent, "Guia de uso", 1000, 680, modal=False)
        self.minsize(760, 460)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._sections: dict[str, str] = {}  # titulo -> marca en el texto

        self.index = ctk.CTkScrollableFrame(self, width=210, corner_radius=0, fg_color=style.SIDEBAR_BG)
        self.index.grid(row=0, column=0, sticky="nsw")
        ctk.CTkLabel(self.index, text="Contenido", font=style.fonts().section, anchor="w").pack(
            fill="x", padx=12, pady=(14, 6)
        )

        self.text_box = ctk.CTkTextbox(self, wrap="word", font=style.fonts().body, corner_radius=0)
        self.text_box.grid(row=0, column=1, sticky="nsew")
        guide = (
            paths.USER_GUIDE_FILE.read_text(encoding="utf-8")
            if paths.USER_GUIDE_FILE.exists()
            else "# Guia de uso\n\nNo se encontro la documentacion."
        )
        self._render_markdown(guide)
        self.text_box.configure(state="disabled")
        if section:
            self.after(80, lambda: self.show_section(section))

    def show_section(self, title: str) -> None:
        """Desplaza la guia para que la seccion ``title`` quede arriba."""
        mark = self._sections.get(title)
        debug_event("Ayuda", "Seccion mostrada: %s", title)
        if mark is None:
            return
        self.text_box._textbox.yview(mark)  # noqa: SLF001
        self.lift()
        self.focus()

    # * Render ----------------------------------------------------------------

    def _render_markdown(self, markdown: str) -> None:
        scaling = ctk.ScalingTracker.get_widget_scaling(self.text_box)
        family = style.FONT_FAMILY

        def size(points: int) -> int:
            return round(points * scaling)

        native = self.text_box._textbox  # noqa: SLF001 - CTkTextbox no expone los tags
        native.configure(padx=28, pady=20, spacing1=2)
        native.tag_configure("h1", font=(family, size(20), "bold"), spacing3=10)
        native.tag_configure("h2", font=(family, size(15), "bold"), spacing1=16, spacing3=6)
        native.tag_configure("h3", font=(family, size(12), "bold"), spacing1=10, spacing3=4)
        native.tag_configure("body", font=(family, size(10)), spacing3=4)
        native.tag_configure("list", font=(family, size(10)), lmargin1=18, lmargin2=34, spacing3=3)
        native.tag_configure("bold", font=(family, size(10), "bold"))
        native.tag_configure("italic", font=(family, size(10), "italic"))
        code_background = style.themed(("gray92", "gray24"))
        native.tag_configure("code", font=("Consolas", size(10)), background=code_background)
        native.tag_configure(
            "codeblock", font=("Consolas", size(9)), background=code_background, wrap="char",
            lmargin1=14, lmargin2=14, rmargin=14, spacing1=2, spacing3=2,
        )

        code_lines: list[str] | None = None
        skip_blank = False  # el titulo ya trae su propio espaciado
        for raw_line in markdown.splitlines():
            line = raw_line.strip()
            if line.startswith("```"):
                if code_lines is None:
                    code_lines = []
                else:
                    self._insert_code_block(native, code_lines)
                    code_lines = None
                continue
            if code_lines is not None:
                code_lines.append(raw_line)
                continue
            if line.startswith(("# ", "## ", "### ")):
                level, title = line.split(" ", 1)
                if level == "#":
                    native.insert("end", title + "\n", "h1")
                else:
                    self._insert_heading(native, title, "h2" if level == "##" else "h3")
                skip_blank = True
                continue
            if not line and skip_blank:
                continue
            skip_blank = False
            if line.startswith(("- ", "* ")):
                self._insert_inline(native, "•  " + line[2:], "list")
            elif line[:1].isdigit() and ". " in line[:4]:
                self._insert_inline(native, line, "list")
            elif line:
                self._insert_inline(native, line, "body")
            native.insert("end", "\n")

    def _insert_heading(self, native: tk.Text, title: str, tag: str) -> None:
        mark = f"section{len(self._sections)}"
        native.mark_set(mark, "end-1c")
        native.mark_gravity(mark, "left")
        self._sections[title] = mark
        native.insert("end", title + "\n", tag)
        # Etiquetas (no botones) para que los titulos largos se ajusten en vez de recortarse.
        level_two = tag == "h2"
        color = style.TEXT if level_two else style.TEXT_MUTED
        entry = ctk.CTkLabel(
            self.index,
            text=title,
            anchor="w",
            justify="left",
            wraplength=170 if level_two else 158,
            text_color=color,
            font=style.fonts().body_bold if level_two else style.fonts().small,
            cursor="hand2",
        )
        entry.pack(fill="x", padx=(14 if level_two else 26, 8), pady=(8 if level_two else 2, 0))
        entry.bind("<Button-1>", lambda _event: self.show_section(title))
        entry.bind("<Enter>", lambda _event: entry.configure(text_color=style.accent_color()))
        entry.bind("<Leave>", lambda _event: entry.configure(text_color=color))

    def _insert_code_block(self, native: tk.Text, lines: list[str]) -> None:
        """Bloque de codigo con fondo propio y boton para copiarlo al portapapeles."""
        code = "\n".join(lines).strip("\n")
        button = ctk.CTkButton(
            native, text="Copiar", width=70, height=24, corner_radius=6, font=style.fonts().small,
        )
        button.configure(command=lambda: self._copy(code, button))
        native.window_create("end", window=button, padx=14, pady=4)
        native.insert("end", "\n")
        native.insert("end", code + "\n", "codeblock")

    def _copy(self, code: str, button: ctk.CTkButton) -> None:
        self.clipboard_clear()
        self.clipboard_append(code)
        button.configure(text="Copiado")
        self.after(1500, lambda: button.winfo_exists() and button.configure(text="Copiar"))

    @staticmethod
    def _insert_inline(native: tk.Text, line: str, base_tag: str) -> None:
        """Inserta una linea respetando **negrita**, *cursiva* y `codigo`."""
        styles = {"bold": False, "italic": False, "code": False}
        token, buffer = 0, ""

        def flush() -> None:
            native.insert("end", buffer, (base_tag, *(name for name, active in styles.items() if active)))

        while token < len(line):
            marker, width = None, 1
            if line[token] == "`":
                marker = "code"
            elif not styles["code"] and line.startswith("**", token):
                marker, width = "bold", 2
            elif not styles["code"] and line[token] == "*":
                marker = "italic"
            if marker:
                flush()
                buffer = ""
                styles[marker] = not styles[marker]
                token += width
                continue
            buffer += line[token]
            token += 1
        flush()


# * Crear firma -------------------------------------------------------------

class SignaturePad(ctk.CTkToplevel):
    """
    Lienzo para dibujar una firma con el mouse o un lapiz digital.

    La firma se guarda como PNG con fondo transparente, recortada al trazo y
    renderizada al triple de resolucion para que se vea nitida en el PDF.
    """

    CANVAS_WIDTH = 640
    CANVAS_HEIGHT = 260
    RENDER_SCALE = 3

    def __init__(self, parent, on_saved: Callable[[Path], None]) -> None:
        super().__init__(parent)
        _prepare_toplevel(self, parent, "Crear firma", 700, 470, modal=True)
        self.resizable(False, False)
        self.on_saved = on_saved
        self.strokes: list[list[tuple[int, int, int]]] = []  # (x, y, grosor)
        self.pen_width = tk.IntVar(value=3)
        self.name = tk.StringVar(value=f"firma_{datetime.now():%Y%m%d_%H%M%S}")

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(18, 8))
        ctk.CTkLabel(header, text="Nombre", font=style.fonts().body).pack(side="left")
        ctk.CTkEntry(header, textvariable=self.name, width=260, height=32).pack(side="left", padx=10)
        ctk.CTkLabel(header, text="Grosor", font=style.fonts().body).pack(side="left", padx=(12, 6))
        width_selector = ctk.CTkSegmentedButton(
            header,
            values=["2", "3", "5"],
            command=lambda value: self.pen_width.set(int(value)),
        )
        width_selector.pack(side="left")
        width_selector.set("3")

        self.canvas = tk.Canvas(
            self,
            width=self.CANVAS_WIDTH,
            height=self.CANVAS_HEIGHT,
            background="white",
            highlightthickness=1,
            highlightbackground="#9e9e9e",
            cursor="pencil",
        )
        self.canvas.pack(padx=20, pady=4)
        self.canvas.create_line(40, 200, self.CANVAS_WIDTH - 40, 200, fill="#d0d0d0", dash=(4, 4), tags="guide")
        self.canvas.bind("<ButtonPress-1>", self._start)
        self.canvas.bind("<B1-Motion>", self._draw)

        ctk.CTkLabel(
            self, text="Dibuje su firma sobre la linea.", font=style.fonts().small, text_color=style.TEXT_MUTED
        ).pack()

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=20, pady=14)
        secondary_button(buttons, "Limpiar", self._clear, "clear", width=110).pack(side="left")
        secondary_button(buttons, "Deshacer", self._undo, "previous", width=110).pack(side="left", padx=8)
        primary_button(buttons, "Guardar firma", self._save, "check", width=150).pack(side="right")
        self.bind("<Control-z>", lambda _event: self._undo())

    def _start(self, event) -> None:
        self.strokes.append([(event.x, event.y, self.pen_width.get())])

    def _draw(self, event) -> None:
        if not self.strokes:
            return
        stroke = self.strokes[-1]
        last_x, last_y, width = stroke[-1]
        self.canvas.create_line(
            last_x, last_y, event.x, event.y,
            width=width, fill="black", capstyle="round", joinstyle="round", smooth=True,
            tags=f"stroke{len(self.strokes)}",
        )
        stroke.append((event.x, event.y, width))

    def _undo(self) -> None:
        debug_event("Firmar", "Lienzo de firma: deshacer trazo", trazos=len(self.strokes))
        if self.strokes:
            self.canvas.delete(f"stroke{len(self.strokes)}")
            self.strokes.pop()

    def _clear(self) -> None:
        debug_event("Firmar", "Lienzo de firma: limpiar", trazos=len(self.strokes))
        self.strokes.clear()
        self.canvas.delete("all")
        self.canvas.create_line(40, 200, self.CANVAS_WIDTH - 40, 200, fill="#d0d0d0", dash=(4, 4), tags="guide")

    def _save(self) -> None:
        strokes = [stroke for stroke in self.strokes if len(stroke) > 1]
        if not strokes:
            messagebox.showwarning("Firma vacia", "Dibuje una firma antes de guardarla.", parent=self)
            return

        scale = self.RENDER_SCALE
        image = Image.new("RGBA", (self.CANVAS_WIDTH * scale, self.CANVAS_HEIGHT * scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        for stroke in strokes:
            width = stroke[0][2] * scale
            points = [(x * scale, y * scale) for x, y, _ in stroke]
            draw.line(points, fill=(0, 0, 0, 255), width=width, joint="curve")
            radius = width / 2
            for x, y in (points[0], points[-1]):
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(0, 0, 0, 255))

        bbox = image.getbbox()
        if bbox:
            margin = 6 * scale
            image = image.crop(
                (max(bbox[0] - margin, 0), max(bbox[1] - margin, 0),
                 min(bbox[2] + margin, image.width), min(bbox[3] + margin, image.height))
            )

        output = signature_path_for(self.name.get(), ".png")
        image.save(output)
        self.destroy()
        self.on_saved(output)
