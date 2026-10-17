"""
Pagina "Firmar": ubica visualmente una imagen de firma sobre el PDF.

Dos modos: firma visual (estampa la imagen) y firma digital con certificado
.pfx/.p12 (PAdES), cuya apariencia combina la imagen opcional con una leyenda.
El visor y el nucleo comparten ``core.signature_rect``, por lo que la posicion
y el tamano que se ven en pantalla son exactamente los del PDF resultante.
"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import pymupdf
from PIL import Image, ImageTk

from ... import core, signatures
from .. import style
from ..dialogs import SignaturePad, ask_certificate_password, ask_password
from ..widgets import (
    Card,
    FileField,
    enable_file_drop,
    field_label,
    hide,
    icon_button,
    muted_label,
    primary_button,
    show,
)
from .base import BasePage

NO_SIGNATURE = "Sin firma"
VISUAL = "Firma visual"
DIGITAL = "Firma digital"
CERTIFICATE_FILETYPES = (("Certificados digitales", "*.pfx *.p12"),)
DEFAULT_ASPECT = 0.4
CERTIFICATE_HOLDER = "Titular del certificado"
VIEWER_MARGIN = 24
ZOOM_STEP = 1.25
ZOOM_LIMITS = (0.3, 5.0)


class SignPage(BasePage):
    name = "Firmar"
    title = "Firmar PDF"
    subtitle = "Coloque su firma sobre el documento: haga clic o arrastrela en la vista previa."
    icon_name = "sign"
    scrollable = False

    def build(self) -> None:
        self.document: pymupdf.Document | None = None
        self.document_path: Path | None = None
        self.page_index = 0
        self.zoom = 1.0
        self.scale = 1.0
        self.offset = (0.0, 0.0)
        self.page_rect = pymupdf.Rect(0, 0, 0, 0)
        self.signature_paths: dict[str, Path] = {}
        self.signature_image: Image.Image | None = None
        self.image_aspect: float | None = None
        self._certificate_holder = CERTIFICATE_HOLDER
        self._drag_offset: tuple[float, float] | None = None
        self._page_photo = None
        self._overlay_photo = None
        self._redraw_pending = False
        self._resize_job: str | None = None
        self._last_canvas_size = (0, 0)

        self.body.grid_columnconfigure(0, weight=0)
        self.body.grid_columnconfigure(1, weight=1)
        self.body.grid_rowconfigure(0, weight=1)
        self._build_panel()
        self._build_viewer()
        self._refresh_signatures()
        self._apply_mode()

    # * Construccion ----------------------------------------------------------

    def _build_panel(self) -> None:
        sidebar = ctk.CTkFrame(self.body, fg_color="transparent", corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsw", padx=(0, style.GAP), pady=(0, style.PAD))
        sidebar.grid_rowconfigure(0, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)
        panel = ctk.CTkScrollableFrame(sidebar, width=330, fg_color="transparent", corner_radius=0)
        panel.grid(row=0, column=0, sticky="ns")
        panel.grid_columnconfigure(0, weight=1)

        self.mode = ctk.CTkSegmentedButton(
            panel, values=[VISUAL, DIGITAL], command=lambda _value: self._apply_mode(), height=34,
            font=style.fonts().body,
        )
        self.mode.set(VISUAL)
        self.mode.grid(row=0, column=0, sticky="ew", pady=(0, style.GAP))

        document = Card(panel, "Documento")
        document.grid(row=1, column=0, sticky="ew", pady=(0, style.GAP))
        self.source_field = FileField(
            document, document.row(0), "PDF a firmar", on_change=self._open_document,
            placeholder="Seleccione o arrastre un PDF", stacked=True,
        )

        signature = Card(panel, "Firma")
        signature.grid(row=2, column=0, sticky="ew", pady=(0, style.GAP))
        selector = ctk.CTkFrame(signature, fg_color="transparent")
        selector.grid(row=signature.row(0), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD, pady=(8, 6))
        selector.grid_columnconfigure(0, weight=1)
        self.signature_combo = ctk.CTkComboBox(
            selector, values=[NO_SIGNATURE], state="readonly", height=34, command=self._on_signature_selected
        )
        self.signature_combo.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        icon_button(selector, "edit", self._draw_signature, "Dibujar firma nueva").grid(row=0, column=1)
        icon_button(selector, "image", self._import_signature, "Importar imagen (PNG/JPG)").grid(row=0, column=2)
        icon_button(selector, "delete", self._delete_signature, "Borrar firma seleccionada").grid(row=0, column=3)
        self.signature_preview = ctk.CTkLabel(
            signature, text="Sin firma seleccionada", height=96, corner_radius=8,
            fg_color=("white", "gray92"), text_color="gray45",
        )
        self.signature_preview.grid(row=signature.row(1), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD, pady=(0, 4))
        self.signature_hint = muted_label(
            signature, "Opcional: la imagen se muestra sobre la leyenda del certificado.", wraplength=290
        )
        self.signature_hint.grid(row=signature.row(2), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD)

        self._build_certificate_card(panel, row=3)

        position = Card(panel, "Posicion")
        position.grid(row=4, column=0, sticky="ew", pady=(0, style.GAP))
        grid = ctk.CTkFrame(position, fg_color="transparent")
        grid.grid(row=position.row(0), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD, pady=(8, 0))
        grid.grid_columnconfigure((1, 3), weight=1)
        self.page_var = tk.StringVar(value="1")
        self.width_var = tk.StringVar(value=str(int(core.DEFAULT_SIGNATURE_WIDTH)))
        self.x_var = tk.StringVar()
        self.y_var = tk.StringVar()
        for index, (label, variable, tip) in enumerate((
            ("Pagina", self.page_var, None),
            ("Ancho", self.width_var, "pt"),
            ("X", self.x_var, "pt"),
            ("Y", self.y_var, "pt"),
        )):
            row, column = divmod(index, 2)
            field_label(grid, label).grid(row=row, column=column * 2, sticky="w", padx=(0 if column == 0 else 12, 6), pady=4)
            ctk.CTkEntry(grid, textvariable=variable, width=70, height=30).grid(
                row=row, column=column * 2 + 1, sticky="ew", pady=4
            )
        self.all_pages = tk.BooleanVar(value=False)
        self.all_pages_check = ctk.CTkCheckBox(
            position, text="Firmar todas las paginas", variable=self.all_pages, font=style.fonts().body,
            command=self._schedule_overlay,
        )
        self.all_pages_check.grid(row=position.row(1), column=0, columnspan=3, sticky="w", padx=style.CARD_PAD, pady=(10, 2))
        muted_label(position, "Medidas en puntos (72 pt = 1 pulgada).").grid(
            row=position.row(2), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD
        )
        for variable in (self.width_var, self.x_var, self.y_var):
            variable.trace_add("write", lambda *_: self._schedule_overlay())
        self.page_var.trace_add("write", lambda *_: self._on_page_typed())

        output = Card(panel, "Resultado")
        output.grid(row=5, column=0, sticky="ew", pady=(0, style.GAP))
        self.output_field = FileField(output, output.row(0), "Guardar como", mode="save", stacked=True,
                                      initial_dir=lambda: self.app.settings.output_path)

        self.run_button = primary_button(sidebar, "Firmar PDF", self._sign, "sign")
        self.run_button.grid(row=1, column=0, sticky="ew", pady=(style.GAP, 0), padx=(0, 14))

    def _build_certificate_card(self, panel, row: int) -> None:
        self.certificate_card = Card(panel, "Certificado digital")
        self.certificate_card.grid(row=row, column=0, sticky="ew", pady=(0, style.GAP))
        card = self.certificate_card
        warning = muted_label(
            card,
            "La firma digital debe ser el ultimo cambio: unir, extraer, proteger o "
            "estampar una firma visual despues de firmar la invalida.",
            wraplength=290,
        )
        warning.configure(text_color=style.WARNING)
        warning.grid(row=card.row(0), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD, pady=(4, 0))
        self.certificate_field = FileField(
            card, card.row(1), "Archivo .pfx / .p12", filetypes=CERTIFICATE_FILETYPES,
            placeholder="Seleccione su certificado", stacked=True,
        )
        details = ctk.CTkFrame(card, fg_color="transparent")
        details.grid(row=card.row(3), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD, pady=(8, 0))
        details.grid_columnconfigure(1, weight=1)
        self.reason_var = tk.StringVar()
        self.location_var = tk.StringVar()
        for index, (label, variable) in enumerate((("Motivo", self.reason_var), ("Lugar", self.location_var))):
            field_label(details, label).grid(row=index, column=0, sticky="w", padx=(0, 8), pady=4)
            ctk.CTkEntry(details, textvariable=variable, placeholder_text="Opcional", height=30).grid(
                row=index, column=1, sticky="ew", pady=4
            )
        self.visible = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            card, text="Mostrar la firma en el documento", variable=self.visible, font=style.fonts().body,
            command=self._schedule_overlay,
        ).grid(row=card.row(4), column=0, columnspan=3, sticky="w", padx=style.CARD_PAD, pady=(10, 6))
        muted_label(
            card, "La contrasena del certificado se pide al firmar y nunca se guarda.", wraplength=290
        ).grid(row=card.row(5), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD)

    def _build_viewer(self) -> None:
        viewer = Card(self.body)
        viewer.grid(row=0, column=1, sticky="nsew", pady=(0, style.PAD))
        viewer.grid_columnconfigure(0, weight=1)
        viewer.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(viewer, fg_color="transparent")
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=8)
        toolbar.grid_columnconfigure(4, weight=1)
        icon_button(toolbar, "first", lambda: self._go_to(0), "Primera pagina").grid(row=0, column=0)
        icon_button(toolbar, "previous", lambda: self._go_to(self.page_index - 1), "Pagina anterior").grid(row=0, column=1)
        self.page_label = ctk.CTkLabel(toolbar, text="Sin documento", width=120, font=style.fonts().body)
        self.page_label.grid(row=0, column=2)
        icon_button(toolbar, "next", lambda: self._go_to(self.page_index + 1), "Pagina siguiente").grid(row=0, column=3, sticky="w")
        icon_button(toolbar, "last", lambda: self._go_to(self._page_count() - 1), "Ultima pagina").grid(row=0, column=4, sticky="w")
        icon_button(toolbar, "zoom_out", lambda: self._set_zoom(self.zoom / ZOOM_STEP), "Alejar (Ctrl + rueda)").grid(row=0, column=5)
        self.zoom_label = ctk.CTkLabel(toolbar, text="100%", width=54, font=style.fonts().body)
        self.zoom_label.grid(row=0, column=6)
        icon_button(toolbar, "zoom_in", lambda: self._set_zoom(self.zoom * ZOOM_STEP), "Acercar (Ctrl + rueda)").grid(row=0, column=7)
        icon_button(toolbar, "fit", lambda: self._set_zoom(1.0), "Ajustar pagina").grid(row=0, column=8, padx=(4, 0))

        self.canvas = tk.Canvas(viewer, highlightthickness=0, background=style.themed(style.CANVAS_BG))
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=(0, 0))
        vertical = ctk.CTkScrollbar(viewer, orientation="vertical", command=self.canvas.yview)
        vertical.grid(row=1, column=1, sticky="ns", padx=(0, 6))
        horizontal = ctk.CTkScrollbar(viewer, orientation="horizontal", command=self.canvas.xview)
        horizontal.grid(row=2, column=0, sticky="ew", padx=(10, 0), pady=(0, 8))
        self.canvas.configure(xscrollcommand=horizontal.set, yscrollcommand=vertical.set)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda _event: setattr(self, "_drag_offset", None))
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        ctk.AppearanceModeTracker.add(self._on_appearance_change, self.canvas)
        enable_file_drop(self.canvas, lambda files: files and self.source_field.set(files[0]), recursive=False)
        self._draw_placeholder()

    # * Modo ------------------------------------------------------------------

    @property
    def digital(self) -> bool:
        return self.mode.get() == DIGITAL

    @property
    def aspect_ratio(self) -> float:
        """Relacion alto/ancho del recuadro de firma segun el modo."""
        if self.digital:
            return core.digital_aspect_ratio(self.image_aspect)
        return self.image_aspect or DEFAULT_ASPECT

    def _apply_mode(self) -> None:
        if self.digital:
            show(self.certificate_card)
            show(self.signature_hint)
            self.all_pages.set(False)
            self.all_pages_check.configure(state="disabled")
            self.run_button.configure(text="Firmar digitalmente")
        else:
            hide(self.certificate_card)
            hide(self.signature_hint)
            self.all_pages_check.configure(state="normal")
            self.run_button.configure(text="Firmar PDF")
        self._schedule_overlay()

    def _overlay_visible(self) -> bool:
        if self.digital:
            return self.visible.get()
        return self.signature_image is not None

    # * Documento -------------------------------------------------------------

    def _open_document(self, path: Path) -> None:
        self._close_document()
        source = self.resolved(path)
        password = self.passwords.get(source)
        retry = False
        while True:
            try:
                self.document = core.open_document(source, password)
                break
            except core.PasswordRequiredError as error:
                password = ask_password(self, source.name, retry=retry or isinstance(error, core.WrongPasswordError))
                retry = True
                if not password:
                    self._draw_placeholder("El documento esta protegido.")
                    return
            except core.PdfManagementError as error:
                self.app.show_error(error)
                self._draw_placeholder()
                return
        if password:
            self.passwords[source] = password
        self.document_path = source
        self.page_index = self.document.page_count - 1 if self.document.page_count else 0
        self.zoom = 1.0
        self.output_field.set(self.default_output(source, "firmado"), auto=True)
        self.page_var.set(str(self.page_index + 1))
        self._render_page()
        if not self.x_var.get() or not self.y_var.get():
            self._place_default()

    def _close_document(self) -> None:
        if self.document is not None:
            self.document.close()
        self.document = None
        self.document_path = None

    def on_close(self) -> None:
        self._close_document()

    def _page_count(self) -> int:
        return self.document.page_count if self.document else 0

    # * Firmas ----------------------------------------------------------------

    def _refresh_signatures(self, select: Path | None = None) -> None:
        files = signatures.list_signatures()
        self.signature_paths = {file.name: file for file in files}
        self.signature_combo.configure(values=[NO_SIGNATURE, *self.signature_paths])
        if select is not None:
            name = select.name
        elif self.signature_combo.get() in self.signature_paths:
            name = self.signature_combo.get()
        else:
            name = files[0].name if files else NO_SIGNATURE
        self.signature_combo.set(name)
        self._on_signature_selected(name)

    def _on_signature_selected(self, name: str) -> None:
        path = self.signature_paths.get(name)
        if path is None:
            self.signature_image = None
            self.image_aspect = None
            self.signature_preview.configure(image=None, text="Sin firma seleccionada")
            self._schedule_overlay()
            return
        try:
            self.signature_image = core.load_signature(path)
            self.image_aspect = core.image_aspect_ratio(self.signature_image)
        except (OSError, core.PdfManagementError):
            self.signature_image = None
            self.image_aspect = None
            self.signature_preview.configure(image=None, text="No se pudo cargar la imagen")
            self._schedule_overlay()
            return
        thumbnail = self.signature_image.copy()
        thumbnail.thumbnail((280, 84))
        self._preview_image = ctk.CTkImage(thumbnail, thumbnail, size=thumbnail.size)
        self.signature_preview.configure(image=self._preview_image, text="")
        self._schedule_overlay()

    def _draw_signature(self) -> None:
        SignaturePad(self, on_saved=lambda path: self._refresh_signatures(select=path))

    def _import_signature(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Importar firma",
            filetypes=(("Imagenes", "*.png *.jpg *.jpeg"), ("PNG", "*.png"), ("JPG", "*.jpg *.jpeg")),
        )
        if chosen:
            self.guard(lambda: self._refresh_signatures(select=signatures.import_signature(chosen)))

    def _delete_signature(self) -> None:
        name = self.signature_combo.get()
        path = self.signature_paths.get(name)
        if path is None:
            return
        if messagebox.askyesno("Borrar firma", f"Desea borrar la firma '{name}'?", parent=self):
            signatures.delete_signature(path)
            self.signature_combo.set(NO_SIGNATURE)
            self._refresh_signatures()

    # * Colocacion ------------------------------------------------------------

    def _placement(self) -> core.SignaturePlacement | None:
        try:
            return core.SignaturePlacement(
                x=float(self.x_var.get()),
                y=float(self.y_var.get()),
                width=float(self.width_var.get()),
                page_number=self.page_index + 1,
                all_pages=self.all_pages.get(),
            )
        except ValueError:
            return None

    def _current_rect(self) -> pymupdf.Rect | None:
        placement = self._placement()
        if placement is None or self.document is None:
            return None
        return core.signature_rect(self.page_rect, placement, self.aspect_ratio)

    def _set_position(self, x: float, y: float) -> None:
        placement = self._placement()
        width = placement.width if placement else core.DEFAULT_SIGNATURE_WIDTH
        rect = core.signature_rect(
            self.page_rect, core.SignaturePlacement(x=x, y=y, width=width), self.aspect_ratio
        )
        self.x_var.set(f"{rect.x0:.1f}")
        self.y_var.set(f"{rect.y0:.1f}")

    def _place_default(self) -> None:
        """Ubicacion inicial: esquina inferior derecha, con margen."""
        try:
            width = float(self.width_var.get())
        except ValueError:
            width = core.DEFAULT_SIGNATURE_WIDTH
        margin = 54
        self._set_position(self.page_rect.width - width - margin, self.page_rect.height - width * self.aspect_ratio - margin)

    def _to_page_point(self, event) -> tuple[float, float]:
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        return (canvas_x - self.offset[0]) / self.scale, (canvas_y - self.offset[1]) / self.scale

    def _on_press(self, event) -> None:
        if self.document is None:
            self.source_field.browse()
            return
        if not self._overlay_visible():
            message = (
                "Active 'Mostrar la firma en el documento' para ubicarla."
                if self.digital
                else "Seleccione, dibuje o importe una firma primero."
            )
            messagebox.showinfo("Firma", message, parent=self)
            return
        x, y = self._to_page_point(event)
        rect = self._current_rect()
        if rect is not None and rect.contains(pymupdf.Point(x, y)):
            self._drag_offset = (x - rect.x0, y - rect.y0)
            return
        width = rect.width if rect is not None else core.DEFAULT_SIGNATURE_WIDTH
        height = rect.height if rect is not None else width * self.aspect_ratio
        self._drag_offset = (width / 2, height / 2)
        self._set_position(x - width / 2, y - height / 2)

    def _on_drag(self, event) -> None:
        if self._drag_offset is None or self.document is None:
            return
        x, y = self._to_page_point(event)
        self._set_position(x - self._drag_offset[0], y - self._drag_offset[1])

    # * Visor -----------------------------------------------------------------

    def _go_to(self, index: int) -> None:
        if self.document is None or not 0 <= index < self._page_count() or index == self.page_index:
            return
        self.page_index = index
        self.page_var.set(str(index + 1))
        self._render_page()

    def _on_page_typed(self) -> None:
        try:
            index = int(self.page_var.get()) - 1
        except ValueError:
            return
        if index != self.page_index:
            self._go_to(index)

    def _set_zoom(self, zoom: float) -> None:
        self.zoom = max(ZOOM_LIMITS[0], min(zoom, ZOOM_LIMITS[1]))
        self._render_page()

    def _on_wheel(self, event) -> None:
        if event.state & 0x0004:  # Ctrl
            self._set_zoom(self.zoom * (ZOOM_STEP if event.delta > 0 else 1 / ZOOM_STEP))
        elif event.state & 0x0001:  # Shift
            self.canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")
        else:
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _on_canvas_resize(self, event) -> None:
        size = (event.width, event.height)
        if size == self._last_canvas_size:
            return
        self._last_canvas_size = size
        if self._resize_job:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(120, self._render_page)

    def _on_appearance_change(self, mode: str) -> None:
        self.canvas.configure(background=style.CANVAS_BG[1] if mode.lower() == "dark" else style.CANVAS_BG[0])

    def _draw_placeholder(self, message: str = "Haga clic aqui o arrastre un PDF para comenzar") -> None:
        self.canvas.delete("all")
        self.canvas.configure(scrollregion=(0, 0, 0, 0))
        width = max(self.canvas.winfo_width(), 400)
        height = max(self.canvas.winfo_height(), 300)
        self.canvas.create_text(
            width / 2, height / 2, text=message, fill=style.themed(style.TEXT_MUTED),
            font=(style.FONT_FAMILY, 12),
        )
        self.page_label.configure(text="Sin documento")

    def _render_page(self) -> None:
        self._resize_job = None
        if self.document is None:
            self._draw_placeholder()
            return
        page = self.document[self.page_index]
        self.page_rect = page.rect
        canvas_width = max(self.canvas.winfo_width(), 200)
        canvas_height = max(self.canvas.winfo_height(), 200)
        fit = min(
            (canvas_width - 2 * VIEWER_MARGIN) / self.page_rect.width,
            (canvas_height - 2 * VIEWER_MARGIN) / self.page_rect.height,
        )
        self.scale = max(fit, 0.05) * self.zoom
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(self.scale, self.scale), alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)
        self._page_photo = ImageTk.PhotoImage(image)

        offset_x = max(VIEWER_MARGIN, (canvas_width - image.width) / 2)
        offset_y = max(VIEWER_MARGIN, (canvas_height - image.height) / 2)
        self.offset = (offset_x, offset_y)
        self.canvas.delete("all")
        self.canvas.create_rectangle(
            offset_x + 3, offset_y + 3, offset_x + image.width + 3, offset_y + image.height + 3,
            fill=style.themed(style.PAGE_SHADOW), outline="",
        )
        self.canvas.create_image(offset_x, offset_y, anchor="nw", image=self._page_photo)
        self.canvas.configure(
            scrollregion=(0, 0, max(canvas_width, image.width + 2 * VIEWER_MARGIN), max(canvas_height, image.height + 2 * VIEWER_MARGIN))
        )
        self.page_label.configure(text=f"Pagina {self.page_index + 1} de {self._page_count()}")
        self.zoom_label.configure(text=f"{self.zoom:.0%}")
        self._draw_overlay()

    def _schedule_overlay(self) -> None:
        if not self._redraw_pending:
            self._redraw_pending = True
            self.after_idle(self._draw_overlay)

    def _draw_overlay(self) -> None:
        self._redraw_pending = False
        self.canvas.delete("overlay")
        rect = self._current_rect()
        if rect is None or not self._overlay_visible():
            return
        x0 = self.offset[0] + rect.x0 * self.scale
        y0 = self.offset[1] + rect.y0 * self.scale
        width = max(int(rect.width * self.scale), 1)
        height = max(int(rect.height * self.scale), 1)
        image_height = height
        if self.digital:
            caption_height = rect.width * core.CAPTION_RATIO * self.scale
            image_height = int(round(height - caption_height))
            self._draw_caption(x0, y0 + height, width, caption_height)
        if self.signature_image is not None and image_height > 0:
            self._overlay_photo = ImageTk.PhotoImage(self.signature_image.resize((width, image_height), Image.LANCZOS))
            self.canvas.create_image(x0, y0, anchor="nw", image=self._overlay_photo, tags="overlay")
        self.canvas.create_rectangle(
            x0 - 2, y0 - 2, x0 + width + 2, y0 + height + 2,
            outline=style.themed(style.accent_color()), dash=(4, 3), width=1.5, tags="overlay",
        )

    def _draw_caption(self, x0: float, bottom: float, width: int, height: float) -> None:
        """Vista previa de la leyenda de la firma digital (misma proporcion que en el PDF)."""
        lines = ("Firmado digitalmente por:", self._certificate_holder, "Fecha: dd/mm/aaaa hh:mm:ss")
        padding = height * 0.08
        longest = max(len(line) for line in lines)
        # Courier: cada caracter mide 0.6 veces el tamano de la fuente.
        size = min((height - 2 * padding) / (len(lines) * 1.2), (width - 2 * padding) / (longest * 0.6))
        if size < 3:
            return
        self.canvas.create_text(
            x0 + padding, bottom - padding, text="\n".join(lines), anchor="sw", justify="left",
            fill="#26263A", font=("Courier New", -int(size)), tags="overlay",
        )

    # * Accion ----------------------------------------------------------------

    def _sign(self) -> None:
        def start() -> None:
            if self.document_path is None:
                raise core.InvalidInputError("Seleccione el PDF a firmar.")
            signature = self.signature_paths.get(self.signature_combo.get())
            if self.digital:
                self._sign_digital(signature)
                return
            if signature is None:
                raise core.InvalidInputError("Seleccione, dibuje o importe una firma.")
            placement = self._placement()
            if placement is None:
                raise core.InvalidInputError("Haga clic en la vista previa para ubicar la firma.")
            output = self.resolve_output(self.output_field)
            if output is None:
                return
            source = self.document_path
            scope = "todas las paginas" if placement.all_pages else f"pagina {placement.page_number}"
            self.run_task(
                f"Firmando {scope}",
                "PDF firmado",
                lambda passwords: core.sign_pdf_with_image(
                    source, output, signature, placement, password=passwords.get(source)
                ),
                button=self.run_button,
            )

        self.guard(start)

    def _sign_digital(self, signature: Path | None) -> None:
        certificate = self.resolved(self.certificate_field.path)
        if certificate is None:
            raise core.InvalidInputError("Seleccione el certificado digital (.pfx o .p12).")
        placement = None
        if self.visible.get():
            placement = self._placement()
            if placement is None:
                raise core.InvalidInputError("Haga clic en la vista previa para ubicar la firma.")
        else:
            signature = None
        output = self.resolve_output(self.output_field)
        if output is None:
            return
        unlocked = self._unlock_certificate(certificate)
        if unlocked is None:
            return
        info, pfx_password = unlocked
        self._certificate_holder = info.subject
        self._schedule_overlay()
        if info.self_signed and not messagebox.askyesno(
            "Certificado autofirmado",
            f"El certificado de '{info.subject}' es autofirmado.\n\n"
            "La firma sera valida, pero programas como Adobe Acrobat mostraran la "
            "identidad del firmante como desconocida.\n\nDesea continuar?",
            parent=self,
        ):
            return
        source = self.document_path
        reason = self.reason_var.get().strip() or None
        location = self.location_var.get().strip() or None
        self.run_task(
            f"Firmando digitalmente como {info.subject}",
            "PDF firmado digitalmente",
            lambda passwords: core.sign_pdf_with_certificate(
                source, output, certificate, pfx_password,
                placement=placement, signature_image=signature, reason=reason, location=location,
                password=passwords.get(source),
            ),
            button=self.run_button,
        )

    def _unlock_certificate(self, certificate: Path) -> tuple[core.CertificateInfo, str] | None:
        """Pide la contrasena del certificado hasta que sea correcta. ``None`` si se cancela."""
        retry = False
        while True:
            pfx_password = ask_certificate_password(self, certificate.name, retry=retry)
            if pfx_password is None:
                return None
            try:
                return core.load_certificate(certificate, pfx_password), pfx_password
            except core.WrongCertificatePasswordError:
                retry = True
