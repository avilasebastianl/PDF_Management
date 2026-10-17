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


# * Ayuda -------------------------------------------------------------------

class HelpWindow(ctk.CTkToplevel):
    """Muestra ``docs/user_guide.md`` con un formato Markdown basico."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        _prepare_toplevel(self, parent, "Guia de uso", 860, 640, modal=False)
        self.minsize(640, 420)
        text_box = ctk.CTkTextbox(self, wrap="word", font=style.fonts().body, corner_radius=0)
        text_box.pack(fill="both", expand=True)
        guide = (
            paths.USER_GUIDE_FILE.read_text(encoding="utf-8")
            if paths.USER_GUIDE_FILE.exists()
            else "# Guia de uso\n\nNo se encontro la documentacion."
        )
        self._render_markdown(text_box, guide)
        text_box.configure(state="disabled")

    @staticmethod
    def _render_markdown(text_box: ctk.CTkTextbox, markdown: str) -> None:
        scaling = ctk.ScalingTracker.get_widget_scaling(text_box)
        family = style.FONT_FAMILY

        def size(points: int) -> int:
            return round(points * scaling)

        native = text_box._textbox  # noqa: SLF001 - CTkTextbox no expone los tags
        native.configure(padx=28, pady=20, spacing1=2)
        native.tag_configure("h1", font=(family, size(20), "bold"), spacing3=10)
        native.tag_configure("h2", font=(family, size(15), "bold"), spacing1=16, spacing3=6)
        native.tag_configure("h3", font=(family, size(12), "bold"), spacing1=10, spacing3=4)
        native.tag_configure("body", font=(family, size(10)), spacing3=4)
        native.tag_configure("list", font=(family, size(10)), lmargin1=18, lmargin2=34, spacing3=3)
        native.tag_configure("code", font=("Consolas", size(10)), background=style.themed(("gray90", "gray25")))
        native.tag_configure("bold", font=(family, size(10), "bold"))

        for raw_line in markdown.splitlines():
            line = raw_line.strip()
            if line.startswith("```"):
                continue
            if line.startswith("### "):
                native.insert("end", line[4:] + "\n", "h3")
            elif line.startswith("## "):
                native.insert("end", line[3:] + "\n", "h2")
            elif line.startswith("# "):
                native.insert("end", line[2:] + "\n", "h1")
            elif line.startswith(("- ", "* ")):
                HelpWindow._insert_inline(native, "•  " + line[2:], "list")
            elif line[:1].isdigit() and ". " in line[:4]:
                HelpWindow._insert_inline(native, line, "list")
            elif line:
                HelpWindow._insert_inline(native, line, "body")
            native.insert("end", "\n")

    @staticmethod
    def _insert_inline(native: tk.Text, line: str, base_tag: str) -> None:
        """Inserta una linea respetando **negrita** y `codigo`."""
        token, buffer, bold, code = 0, "", False, False
        while token < len(line):
            if line.startswith("**", token):
                native.insert("end", buffer, (base_tag, "bold") if bold else base_tag)
                buffer, bold, token = "", not bold, token + 2
                continue
            if line[token] == "`":
                native.insert("end", buffer, (base_tag, "code") if code else base_tag)
                buffer, code, token = "", not code, token + 1
                continue
            buffer += line[token]
            token += 1
        native.insert("end", buffer, base_tag)


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
        if self.strokes:
            self.canvas.delete(f"stroke{len(self.strokes)}")
            self.strokes.pop()

    def _clear(self) -> None:
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
