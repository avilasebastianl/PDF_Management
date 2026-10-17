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
from ...core.signing import MIN_SIGNATURE_WIDTH
from .. import style
from ..dialogs import SignaturePad, ask_certificate_password, ask_password
from ..dropdown import dropdown_menu, set_dropdown_values
from ..icons import GLYPHS, icon, render_glyph
from ..widgets import (
    Card,
    FileField,
    ToolTip,
    enable_file_drop,
    field_label,
    hide,
    icon_button,
    muted_label,
    primary_button,
    set_enabled,
    set_label_image,
    show,
)
from .base import BasePage

NO_SIGNATURE = "Sin firma"
VISUAL = "Firma visual"
DIGITAL = "Firma digital"
CERTIFICATE_FILETYPES = (("Certificados digitales", "*.pfx *.p12"),)
DEFAULT_ASPECT = 0.4
CERTIFICATE_HOLDER = "Titular del certificado"
CERTIFICATE_GUIDE_SECTION = "Como obtener un certificado digital"  # titulo en docs/user_guide.md
VIEWER_MARGIN = 24
PLACEHOLDER_EMPTY = (
    "Haga clic aqui o arrastre un PDF para comenzar",
    'Tambien puede usar el boton "Examinar" del panel. Solo archivos PDF.',
)
PLACEHOLDER_LOCKED = (
    "El documento esta protegido",
    "Seleccionelo de nuevo e ingrese su contrasena para verlo.",
)
ZOOM_STEP = 1.25
ZOOM_LIMITS = (0.3, 5.0)
HANDLE_SIZE = 9          # lado de las asas de redimensionado, en pixeles del visor
SIZE_STEP = 10           # paso de los botones - / + del tamano, en puntos
SIZE_SLIDER_MAX = 400    # ancho maximo del deslizador (se ajusta a la pagina)
_CORNER_CURSORS = {"nw": "size_nw_se", "se": "size_nw_se", "ne": "size_ne_sw", "sw": "size_ne_sw"}


def _glyph_image(name: str, size: int, color: str) -> Image.Image:
    """Icono de la fuente del sistema como imagen PIL (para dibujar en el lienzo)."""
    image = render_glyph(GLYPHS[name], size, color)
    return image.resize((size, size), Image.LANCZOS) if image else Image.new("RGBA", (size, size), (0, 0, 0, 0))


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
        # Redimensionado con las asas: esquina tomada y esquina opuesta fija (en puntos).
        self._resize_corner: str | None = None
        self._resize_anchor: tuple[float, float] = (0.0, 0.0)
        self._syncing_size = False
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
        self.signature_card = signature
        signature.grid(row=2, column=0, sticky="ew", pady=(0, style.GAP))
        selector = ctk.CTkFrame(signature, fg_color="transparent")
        selector.grid(row=signature.row(0), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD, pady=(8, 6))
        selector.grid_columnconfigure(0, weight=1)
        # Lista de la biblioteca de firmas: muestra 6 y se desplaza si hay mas.
        self.signature_menu = dropdown_menu(
            selector, [NO_SIGNATURE], self._on_signature_selected, max_visible=6, width=160, height=34,
        )
        self.signature_menu.grid(row=0, column=0, sticky="ew", padx=(0, 6))
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
        field_label(grid, "Tamano").grid(row=2, column=0, sticky="w", padx=(0, 6), pady=(8, 4))
        sizer = ctk.CTkFrame(grid, fg_color="transparent")
        sizer.grid(row=2, column=1, columnspan=3, sticky="ew", pady=(8, 4))
        sizer.grid_columnconfigure(1, weight=1)
        icon_button(sizer, "minus", lambda: self._step_size(-SIZE_STEP), "Achicar la firma", size=28).grid(row=0, column=0)
        self.size_slider = ctk.CTkSlider(
            sizer, from_=MIN_SIGNATURE_WIDTH, to=SIZE_SLIDER_MAX, command=self._on_size_slider, height=16,
        )
        self.size_slider.set(core.DEFAULT_SIGNATURE_WIDTH)
        self.size_slider.grid(row=0, column=1, sticky="ew", padx=4)
        icon_button(sizer, "add", lambda: self._step_size(SIZE_STEP), "Agrandar la firma", size=28).grid(row=0, column=2)
        self.all_pages = tk.BooleanVar(value=False)
        self.all_pages_check = ctk.CTkCheckBox(
            position, text="Firmar todas las paginas", variable=self.all_pages, font=style.fonts().body,
            command=self._schedule_overlay,
        )
        self.all_pages_check.grid(row=position.row(1), column=0, columnspan=3, sticky="w", padx=style.CARD_PAD, pady=(10, 2))
        muted_label(position, "Arrastre las esquinas del recuadro para cambiar el tamano. Medidas en puntos (72 pt = 1 pulgada).", wraplength=290).grid(
            row=position.row(2), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD
        )
        for variable in (self.width_var, self.x_var, self.y_var):
            variable.trace_add("write", lambda *_: self._schedule_overlay())
        self.width_var.trace_add("write", lambda *_: self._sync_size_slider())
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
        # Acceso directo a la guia: una sola linea, no ocupa espacio en el panel.
        guide_link = ctk.CTkButton(
            card,
            text="  No tiene certificado? Vea como obtenerlo",
            image=icon("info", 14, style.link_color()),
            anchor="w",
            height=24,
            fg_color="transparent",
            hover_color=style.HOVER,
            text_color=style.link_color(),
            font=style.fonts().small,
            command=lambda: self.app.open_help(CERTIFICATE_GUIDE_SECTION),
        )
        guide_link.grid(row=card.row(3), column=0, columnspan=3, sticky="w", padx=style.CARD_PAD - 6, pady=(6, 0))
        ToolTip(guide_link, "Abre la guia: certificados reales y de prueba, y como verificar la firma")
        details = ctk.CTkFrame(card, fg_color="transparent")
        details.grid(row=card.row(4), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD, pady=(8, 0))
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
        ).grid(row=card.row(5), column=0, columnspan=3, sticky="w", padx=style.CARD_PAD, pady=(10, 6))
        muted_label(
            card, "La contrasena del certificado se pide al firmar y nunca se guarda.", wraplength=290
        ).grid(row=card.row(6), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD)

    def _build_viewer(self) -> None:
        viewer = Card(self.body)
        viewer.grid(row=0, column=1, sticky="nsew", pady=(0, style.PAD))
        # Card reparte el ancho entre sus columnas; aqui el lienzo ocupa todo.
        viewer.grid_columnconfigure(0, weight=1, minsize=0)
        viewer.grid_columnconfigure(1, weight=0, minsize=0)
        viewer.grid_rowconfigure(2, weight=1)

        # Barra de herramientas: navegacion | nombre del documento | zoom
        toolbar = ctk.CTkFrame(viewer, fg_color="transparent")
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 8))
        toolbar.grid_columnconfigure(1, weight=1)

        navigation = ctk.CTkFrame(toolbar, fg_color="transparent")
        navigation.grid(row=0, column=0, sticky="w")
        first = icon_button(navigation, "first", lambda: self._go_to(0), "Primera pagina")
        previous = icon_button(navigation, "previous", lambda: self._go_to(self.page_index - 1), "Pagina anterior")
        self.page_label = ctk.CTkLabel(navigation, text="", width=118, font=style.fonts().body)
        following = icon_button(navigation, "next", lambda: self._go_to(self.page_index + 1), "Pagina siguiente")
        last = icon_button(navigation, "last", lambda: self._go_to(self._page_count() - 1), "Ultima pagina")
        for widget in (first, previous, self.page_label, following, last):
            widget.pack(side="left", padx=1)

        self.document_label = ctk.CTkLabel(toolbar, text="", font=style.fonts().small, text_color=style.TEXT_MUTED)
        self.document_label.grid(row=0, column=1, sticky="ew", padx=12)

        zoom = ctk.CTkFrame(toolbar, fg_color="transparent")
        zoom.grid(row=0, column=2, sticky="e")
        zoom_out = icon_button(zoom, "zoom_out", lambda: self._set_zoom(self.zoom / ZOOM_STEP), "Alejar (Ctrl + rueda)")
        self.zoom_label = ctk.CTkLabel(zoom, text="", width=52, font=style.fonts().body)
        zoom_in = icon_button(zoom, "zoom_in", lambda: self._set_zoom(self.zoom * ZOOM_STEP), "Acercar (Ctrl + rueda)")
        fit = icon_button(zoom, "fit", lambda: self._set_zoom(1.0), "Ajustar pagina a la ventana")
        for widget in (zoom_out, self.zoom_label, zoom_in, fit):
            widget.pack(side="left", padx=1)
        self._viewer_buttons = [first, previous, following, last, zoom_out, zoom_in, fit]
        self._nav_buttons = {"first": first, "previous": previous, "next": following, "last": last}
        self._zoom_buttons = {"out": zoom_out, "in": zoom_in}

        ctk.CTkFrame(viewer, height=1, corner_radius=0, fg_color=style.CARD_BORDER).grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=1
        )

        self.canvas = tk.Canvas(viewer, highlightthickness=0, background=style.themed(style.CANVAS_BG))
        self.canvas.grid(row=2, column=0, sticky="nsew", padx=(12, 12), pady=(12, 12))
        self.vertical_scroll = ctk.CTkScrollbar(viewer, orientation="vertical", command=self.canvas.yview)
        self.vertical_scroll.grid(row=2, column=1, sticky="ns", padx=(0, 8), pady=(12, 12))
        self.horizontal_scroll = ctk.CTkScrollbar(viewer, orientation="horizontal", command=self.canvas.xview)
        self.horizontal_scroll.grid(row=3, column=0, sticky="ew", padx=(12, 12), pady=(0, 10))
        self.canvas.configure(xscrollcommand=self.horizontal_scroll.set, yscrollcommand=self.vertical_scroll.set)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        ctk.AppearanceModeTracker.add(self._on_appearance_change, self.canvas)
        enable_file_drop(self.canvas, lambda files: files and self.source_field.set(files[0]), recursive=False)
        self._placeholder = PLACEHOLDER_EMPTY
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
        # Lo principal de cada modo va primero: en firma digital el certificado
        # sube antes de la imagen (opcional), asi no hace falta desplazarse.
        card_options = {"column": 0, "sticky": "ew", "pady": (0, style.GAP)}
        if self.digital:
            self.certificate_card.grid(row=2, **card_options)
            self.signature_card.grid(row=3, **card_options)
            show(self.signature_hint)
            self.all_pages.set(False)
            self.all_pages_check.configure(state="disabled")
            self.run_button.configure(text="Firmar digitalmente")
        else:
            hide(self.certificate_card)
            self.signature_card.grid(row=2, **card_options)
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
                    self._draw_placeholder(PLACEHOLDER_LOCKED)
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
        set_dropdown_values(self.signature_menu, [NO_SIGNATURE, *self.signature_paths])
        if select is not None:
            name = select.name
        elif self.signature_menu.get() in self.signature_paths:
            name = self.signature_menu.get()
        else:
            name = files[0].name if files else NO_SIGNATURE
        self.signature_menu.set(name)
        self._on_signature_selected(name)

    def _select_signature(self, name: str) -> None:
        """Elige una firma de la biblioteca (o "Sin firma") y actualiza la vista previa."""
        self.signature_menu.set(name)
        self._on_signature_selected(name)

    def _on_signature_selected(self, name: str) -> None:
        path = self.signature_paths.get(name)
        if path is None:
            self.signature_image = None
            self.image_aspect = None
            self._show_preview(None, "Sin firma seleccionada")
            self._schedule_overlay()
            return
        try:
            self.signature_image = core.load_signature(path)
            self.image_aspect = core.image_aspect_ratio(self.signature_image)
        except (OSError, core.PdfManagementError):
            self.signature_image = None
            self.image_aspect = None
            self._show_preview(None, "No se pudo cargar la imagen")
            self._schedule_overlay()
            return
        thumbnail = self.signature_image.copy()
        thumbnail.thumbnail((280, 84))
        self._show_preview(ctk.CTkImage(thumbnail, thumbnail, size=thumbnail.size), "")
        self._schedule_overlay()

    def _show_preview(self, image: ctk.CTkImage | None, text: str) -> None:
        """Actualiza la miniatura sin dejar imagenes pegadas ni referencias liberadas."""
        set_label_image(self.signature_preview, image, text)
        # La referencia se reemplaza despues de desvincular la anterior del widget.
        self._preview_image = image

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
        name = self.signature_menu.get()
        path = self.signature_paths.get(name)
        if path is None:
            return
        if messagebox.askyesno("Borrar firma", f"Desea borrar la firma '{name}'?", parent=self):
            signatures.delete_signature(path)
            self.signature_menu.set(NO_SIGNATURE)
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
        corner = self._corner_at(x, y, rect)
        if corner is not None:
            # La esquina opuesta queda fija mientras se arrastra.
            self._resize_corner = corner
            self._resize_anchor = (
                rect.x1 if "w" in corner else rect.x0,
                rect.y1 if "n" in corner else rect.y0,
            )
            return
        if rect is not None and rect.contains(pymupdf.Point(x, y)):
            self._drag_offset = (x - rect.x0, y - rect.y0)
            return
        width = rect.width if rect is not None else core.DEFAULT_SIGNATURE_WIDTH
        height = rect.height if rect is not None else width * self.aspect_ratio
        self._drag_offset = (width / 2, height / 2)
        self._set_position(x - width / 2, y - height / 2)

    def _on_drag(self, event) -> None:
        if self.document is None:
            return
        x, y = self._to_page_point(event)
        if self._resize_corner is not None:
            anchor_x, anchor_y = self._resize_anchor
            # Mantiene la proporcion: manda el eje en el que mas se movio el cursor.
            width = max(abs(x - anchor_x), abs(y - anchor_y) / self.aspect_ratio)
            self._apply_size(width, self._resize_corner, self._resize_anchor)
        elif self._drag_offset is not None:
            self._set_position(x - self._drag_offset[0], y - self._drag_offset[1])

    def _on_release(self, _event) -> None:
        self._drag_offset = None
        self._resize_corner = None

    def _on_motion(self, event) -> None:
        """Cursor segun lo que hay debajo: asa (redimensionar), firma (mover) o pagina."""
        if self.document is None:
            cursor = "hand2"
        elif not self._overlay_visible():
            cursor = ""
        else:
            x, y = self._to_page_point(event)
            rect = self._current_rect()
            corner = self._corner_at(x, y, rect)
            if corner is not None:
                cursor = _CORNER_CURSORS[corner]
            elif rect is not None and rect.contains(pymupdf.Point(x, y)):
                cursor = "fleur"
            else:
                cursor = "crosshair"
        if self.canvas.cget("cursor") != cursor:
            self.canvas.configure(cursor=cursor)

    def _corner_at(self, x: float, y: float, rect: pymupdf.Rect | None) -> str | None:
        """Esquina del recuadro bajo el punto ``(x, y)`` (en puntos), si la hay."""
        if rect is None or not self._overlay_visible():
            return None
        tolerance = HANDLE_SIZE / self.scale
        for name, (corner_x, corner_y) in (
            ("nw", (rect.x0, rect.y0)), ("ne", (rect.x1, rect.y0)),
            ("sw", (rect.x0, rect.y1)), ("se", (rect.x1, rect.y1)),
        ):
            if abs(x - corner_x) <= tolerance and abs(y - corner_y) <= tolerance:
                return name
        return None

    # * Tamano ----------------------------------------------------------------

    def _apply_size(self, width: float, corner: str | None = None, anchor: tuple[float, float] | None = None) -> None:
        """
        Cambia el ancho de la firma (el alto sigue la proporcion). Con ``corner``
        y ``anchor`` crece desde la esquina opuesta; sin ellos, desde el centro.
        """
        if self.document is None or self._current_rect() is None:
            self.width_var.set(f"{max(width, MIN_SIGNATURE_WIDTH):.0f}")
            return
        aspect = self.aspect_ratio
        width = max(MIN_SIGNATURE_WIDTH, min(width, self.page_rect.width, self.page_rect.height / aspect))
        height = width * aspect
        if corner is None or anchor is None:
            current = self._current_rect()
            center_x, center_y = (current.x0 + current.x1) / 2, (current.y0 + current.y1) / 2
            x, y = center_x - width / 2, center_y - height / 2
        else:
            x = anchor[0] - width if "w" in corner else anchor[0]
            y = anchor[1] - height if "n" in corner else anchor[1]
        rect = core.signature_rect(self.page_rect, core.SignaturePlacement(x=x, y=y, width=width), aspect)
        self.width_var.set(f"{rect.width:.1f}")
        self.x_var.set(f"{rect.x0:.1f}")
        self.y_var.set(f"{rect.y0:.1f}")

    def _step_size(self, delta: float) -> None:
        try:
            width = float(self.width_var.get())
        except ValueError:
            width = core.DEFAULT_SIGNATURE_WIDTH
        self._apply_size(width + delta)

    def _on_size_slider(self, value: float) -> None:
        if not self._syncing_size:
            self._apply_size(value)

    def _sync_size_slider(self) -> None:
        """Refleja en el deslizador el ancho escrito o arrastrado."""
        try:
            width = float(self.width_var.get())
        except ValueError:
            return
        self._syncing_size = True
        try:
            self.size_slider.set(width)
        finally:
            self._syncing_size = False

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
        # Los colores del lienzo se fijan al dibujar: se repinta con el tema nuevo.
        if self.document is None:
            self._draw_placeholder()
        else:
            self._render_page()

    def _draw_placeholder(self, placeholder: tuple[str, str] | None = None) -> None:
        """
        Zona para soltar un PDF: recuadro punteado con icono, titulo y ayuda,
        siempre centrados en el area visible del visor.
        """
        if placeholder is not None:
            self._placeholder = placeholder
        title, subtitle = self._placeholder
        canvas = self.canvas
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 50 or height < 50:  # aun sin mapear: se redibuja en <Configure>
            width, height = 640, 480
        canvas.configure(scrollregion=(0, 0, width, height))
        canvas.xview_moveto(0)
        canvas.yview_moveto(0)
        self._update_scrollbars(width, height, width, height)

        scaling = ctk.ScalingTracker.get_widget_scaling(self)
        muted = style.themed(style.TEXT_MUTED)
        inset = 16
        text_width = max(width - 2 * inset - 40, 200)
        canvas.create_rectangle(inset, inset, width - inset, height - inset, outline=muted, dash=(6, 5), width=1.5)
        center_x, center_y = width / 2, height / 2
        self._placeholder_icon = ImageTk.PhotoImage(_glyph_image("pdf", round(52 * scaling), muted))
        canvas.create_image(center_x, center_y - 34 * scaling, image=self._placeholder_icon, anchor="center")
        canvas.create_text(
            center_x, center_y + 14 * scaling, text=title, anchor="center", justify="center", width=text_width,
            fill=style.themed(style.TEXT), font=(style.FONT_FAMILY, round(13 * scaling), "bold"),
        )
        canvas.create_text(
            center_x, center_y + 40 * scaling, text=subtitle, anchor="center", justify="center", width=text_width,
            fill=muted, font=(style.FONT_FAMILY, round(10 * scaling)),
        )
        self.page_label.configure(text="Sin documento")
        self.document_label.configure(text="")
        self.zoom_label.configure(text="—")
        for button in self._viewer_buttons:
            set_enabled(button, False)

    def _update_scrollbars(self, content_width: float, content_height: float, canvas_width: int, canvas_height: int) -> None:
        """Muestra cada barra de desplazamiento solo si el contenido no cabe."""
        (show if content_width > canvas_width + 1 else hide)(self.horizontal_scroll)
        (show if content_height > canvas_height + 1 else hide)(self.vertical_scroll)

    def _render_page(self) -> None:
        self._resize_job = None
        if self.document is None:
            self._draw_placeholder()
            return
        page = self.document[self.page_index]
        self.page_rect = page.rect
        self.size_slider.configure(to=max(MIN_SIGNATURE_WIDTH + 10, min(SIZE_SLIDER_MAX, self.page_rect.width)))
        self._sync_size_slider()
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
        content_width = image.width + 2 * VIEWER_MARGIN
        content_height = image.height + 2 * VIEWER_MARGIN
        self.canvas.configure(scrollregion=(0, 0, max(canvas_width, content_width), max(canvas_height, content_height)))
        self._update_scrollbars(content_width, content_height, canvas_width, canvas_height)
        self.page_label.configure(text=f"Pagina {self.page_index + 1} de {self._page_count()}")
        self.document_label.configure(text=self.document_path.name if self.document_path else "")
        self.zoom_label.configure(text=f"{self.zoom:.0%}")
        # Cada boton se activa solo si su accion tiene efecto en la posicion actual.
        at_first, at_last = self.page_index == 0, self.page_index >= self._page_count() - 1
        set_enabled(self._nav_buttons["first"], not at_first)
        set_enabled(self._nav_buttons["previous"], not at_first)
        set_enabled(self._nav_buttons["next"], not at_last)
        set_enabled(self._nav_buttons["last"], not at_last)
        set_enabled(self._zoom_buttons["out"], self.zoom > ZOOM_LIMITS[0] + 1e-6)
        set_enabled(self._zoom_buttons["in"], self.zoom < ZOOM_LIMITS[1] - 1e-6)
        set_enabled(self._viewer_buttons[-1], True)
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
        accent = style.themed(style.accent_color())
        self.canvas.create_rectangle(
            x0 - 2, y0 - 2, x0 + width + 2, y0 + height + 2,
            outline=accent, dash=(4, 3), width=1.5, tags="overlay",
        )
        half = HANDLE_SIZE / 2
        for corner_x, corner_y in ((x0, y0), (x0 + width, y0), (x0, y0 + height), (x0 + width, y0 + height)):
            self.canvas.create_rectangle(
                corner_x - half, corner_y - half, corner_x + half, corner_y + half,
                fill="white", outline=accent, width=1.5, tags="overlay",
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
            signature = self.signature_paths.get(self.signature_menu.get())
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
