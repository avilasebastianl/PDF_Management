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
from ...i18n import tr
from .. import style
from ..dialogs import SignaturePad, ask_certificate_password, ask_password
from ..dropdown import dropdown_menu, set_dropdown_values
from ..icons import icon
from ..viewer import PageView, Tool, ViewerToolbar
from ..widgets import (
    Card,
    FileField,
    ToolTip,
    field_label,
    hide,
    icon_button,
    muted_label,
    primary_button,
    set_label_image,
    show,
)
from .base import BasePage

NO_SIGNATURE = tr("Sin firma")
VISUAL = tr("Firma visual")
DIGITAL = tr("Firma digital")
CERTIFICATE_FILETYPES = ((tr("Certificados digitales"), "*.pfx *.p12"),)
DEFAULT_ASPECT = 0.4
CERTIFICATE_HOLDER = tr("Titular del certificado")
# Titulo de la seccion en la guia del idioma activo (docs/user_guide*.md): la traduccion
# debe coincidir con el encabezado de la guia traducida.
CERTIFICATE_GUIDE_SECTION = tr("Cómo obtener un certificado digital")
PLACEHOLDER_EMPTY = (
    tr("Haga clic aquí o arrastre un PDF para comenzar"),
    tr('También puede usar el botón "Examinar" del panel. Solo archivos PDF.'),
)
PLACEHOLDER_LOCKED = (
    tr("El documento está protegido"),
    tr("Selecciónelo de nuevo e ingrese su contraseña para verlo."),
)
HANDLE_SIZE = 9  # lado de las asas de redimensionado, en pixeles del visor
SIZE_STEP = 10  # paso de los botones - / + del tamano, en puntos
SIZE_SLIDER_MAX = 400  # ancho maximo del deslizador (se ajusta a la pagina)
_CORNER_CURSORS = {"nw": "size_nw_se", "se": "size_nw_se", "ne": "size_ne_sw", "sw": "size_ne_sw"}


class _SignatureTool(Tool):
    """La firma como herramienta del visor: delega en la pagina Firmar."""

    cursor = "crosshair"

    def __init__(self, page: "SignPage") -> None:
        self.page = page

    def press(self, view, event, hit) -> None:
        self.page.on_pointer_press(event)

    def drag(self, view, event, hit) -> None:
        self.page.on_pointer_drag(event)

    def release(self, view, event, hit) -> None:
        self.page.on_pointer_release(event)

    def motion(self, view, event, hit) -> None:
        self.page.on_pointer_motion(event)

    def draw(self, view) -> None:
        self.page.draw_overlay()


class SignPage(BasePage):
    name = "Firmar"
    title = tr("Firmar PDF")
    subtitle = tr("Coloque su firma sobre el documento: haga clic o arrástrela en la vista previa.")
    icon_name = "sign"
    scrollable = False

    def build(self) -> None:
        self.document: pymupdf.Document | None = None
        self.document_path: Path | None = None
        self.signature_paths: dict[str, Path] = {}
        self.signature_image: Image.Image | None = None
        self.image_aspect: float | None = None
        self._certificate_holder = CERTIFICATE_HOLDER
        self._drag_offset: tuple[float, float] | None = None
        # Redimensionado con las asas: esquina tomada y esquina opuesta fija (en puntos).
        self._interaction: str | None = None  # "mover", "colocar" o "redimensionar" (para el registro)
        self._logged_signature: str | None = None
        self._size_log_job: str | None = None
        self._resize_corner: str | None = None
        self._resize_anchor: tuple[float, float] = (0.0, 0.0)
        self._syncing_size = False
        self._overlay_photo: ImageTk.PhotoImage | None = None
        self._redraw_pending = False

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
            panel,
            values=[VISUAL, DIGITAL],
            command=self._on_mode_selected,
            height=34,
            font=style.fonts().body,
        )
        self.mode.set(VISUAL)
        self.mode.grid(row=0, column=0, sticky="ew", pady=(0, style.GAP))

        document = Card(panel, tr("Documento"))
        document.grid(row=1, column=0, sticky="ew", pady=(0, style.GAP))
        self.source_field = FileField(
            document,
            document.row(0),
            tr("PDF a firmar"),
            on_change=self._open_document,
            placeholder=tr("Seleccione o arrastre un PDF"),
            stacked=True,
            on_clear=self.close_source,
        )

        signature = Card(panel, tr("Firma"))
        self.signature_card = signature
        signature.grid(row=2, column=0, sticky="ew", pady=(0, style.GAP))
        selector = ctk.CTkFrame(signature, fg_color="transparent")
        selector.grid(row=signature.row(0), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD, pady=(8, 6))
        selector.grid_columnconfigure(0, weight=1)
        # Lista de la biblioteca de firmas: muestra 6 y se desplaza si hay mas.
        self.signature_menu = dropdown_menu(
            selector,
            [NO_SIGNATURE],
            self._on_signature_selected,
            width=160,
            height=34,
        )
        self.signature_menu.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        icon_button(selector, "edit", self._draw_signature, tr("Dibujar firma nueva")).grid(row=0, column=1)
        icon_button(selector, "image", self._import_signature, tr("Importar imagen (PNG/JPG)")).grid(row=0, column=2)
        icon_button(selector, "delete", self._delete_signature, tr("Borrar firma seleccionada")).grid(row=0, column=3)
        self.signature_preview = ctk.CTkLabel(
            signature,
            text=tr("Sin firma seleccionada"),
            height=96,
            corner_radius=8,
            fg_color=("white", "gray92"),
            text_color="gray45",
        )
        self.signature_preview.grid(
            row=signature.row(1), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD, pady=(0, 4)
        )
        self.signature_hint = muted_label(
            signature, tr("Opcional: la imagen se muestra sobre la leyenda del certificado."), wraplength=290
        )
        self.signature_hint.grid(row=signature.row(2), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD)

        self._build_certificate_card(panel, row=3)

        position = Card(panel, tr("Posición"))
        position.grid(row=4, column=0, sticky="ew", pady=(0, style.GAP))
        grid = ctk.CTkFrame(position, fg_color="transparent")
        grid.grid(row=position.row(0), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD, pady=(8, 0))
        grid.grid_columnconfigure((1, 3), weight=1)
        self.page_var = tk.StringVar(value="1")
        self.width_var = tk.StringVar(value=str(int(core.DEFAULT_SIGNATURE_WIDTH)))
        self.x_var = tk.StringVar()
        self.y_var = tk.StringVar()
        for index, (label, variable, _tip) in enumerate(
            (
                (tr("Página"), self.page_var, None),
                (tr("Ancho"), self.width_var, "pt"),
                ("X", self.x_var, "pt"),
                ("Y", self.y_var, "pt"),
            )
        ):
            row, column = divmod(index, 2)
            field_label(grid, label).grid(
                row=row, column=column * 2, sticky="w", padx=(0 if column == 0 else 12, 6), pady=4
            )
            ctk.CTkEntry(grid, textvariable=variable, width=70, height=30).grid(
                row=row, column=column * 2 + 1, sticky="ew", pady=4
            )
        field_label(grid, tr("Tamaño")).grid(row=2, column=0, sticky="w", padx=(0, 6), pady=(8, 4))
        sizer = ctk.CTkFrame(grid, fg_color="transparent")
        sizer.grid(row=2, column=1, columnspan=3, sticky="ew", pady=(8, 4))
        sizer.grid_columnconfigure(1, weight=1)
        icon_button(sizer, "minus", lambda: self._step_size(-SIZE_STEP), tr("Achicar la firma"), size=28).grid(
            row=0, column=0
        )
        self.size_slider = ctk.CTkSlider(
            sizer,
            from_=MIN_SIGNATURE_WIDTH,
            to=SIZE_SLIDER_MAX,
            command=self._on_size_slider,
            height=16,
        )
        self.size_slider.set(core.DEFAULT_SIGNATURE_WIDTH)
        self.size_slider.grid(row=0, column=1, sticky="ew", padx=4)
        icon_button(sizer, "add", lambda: self._step_size(SIZE_STEP), tr("Agrandar la firma"), size=28).grid(
            row=0, column=2
        )
        self.all_pages = tk.BooleanVar(value=False)
        self.all_pages_check = ctk.CTkCheckBox(
            position,
            text=tr("Firmar todas las páginas"),
            variable=self.all_pages,
            font=style.fonts().body,
            command=self._on_all_pages_toggled,
        )
        self.all_pages_check.grid(
            row=position.row(1), column=0, columnspan=3, sticky="w", padx=style.CARD_PAD, pady=(10, 2)
        )
        muted_label(
            position,
            tr("Arrastre las esquinas del recuadro para cambiar el tamaño. Medidas en puntos (72 pt = 1 pulgada)."),
            wraplength=290,
        ).grid(row=position.row(2), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD)
        for variable in (self.width_var, self.x_var, self.y_var):
            variable.trace_add("write", lambda *_: self._schedule_overlay())
        self.width_var.trace_add("write", lambda *_: self._sync_size_slider())
        self.page_var.trace_add("write", lambda *_: self._on_page_typed())

        output = Card(panel, tr("Resultado"))
        output.grid(row=5, column=0, sticky="ew", pady=(0, style.GAP))
        self.output_field = FileField(
            output,
            output.row(0),
            tr("Guardar como"),
            mode="save",
            stacked=True,
            initial_dir=lambda: self.app.settings.output_path,
        )

        self.run_button = primary_button(sidebar, tr("Firmar PDF"), self._sign, "sign")
        self.run_button.grid(row=1, column=0, sticky="ew", pady=(style.GAP, 0), padx=(0, 14))

    def _build_certificate_card(self, panel, row: int) -> None:
        self.certificate_card = Card(panel, tr("Certificado digital"))
        self.certificate_card.grid(row=row, column=0, sticky="ew", pady=(0, style.GAP))
        card = self.certificate_card
        warning = muted_label(
            card,
            tr(
                "La firma digital debe ser el último cambio: unir, extraer, proteger o "
                "estampar una firma visual después de firmar la invalida."
            ),
            wraplength=290,
        )
        warning.configure(text_color=style.WARNING)
        warning.grid(row=card.row(0), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD, pady=(4, 0))
        self.certificate_field = FileField(
            card,
            card.row(1),
            tr("Archivo .pfx / .p12"),
            filetypes=CERTIFICATE_FILETYPES,
            placeholder=tr("Seleccione su certificado"),
            stacked=True,
        )
        # Acceso directo a la guia: una sola linea, no ocupa espacio en el panel.
        guide_link = ctk.CTkButton(
            card,
            text="  " + tr("¿No tiene certificado? Vea cómo obtenerlo"),
            image=icon("info", 14, style.link_color()),
            anchor="w",
            height=24,
            fg_color="transparent",
            hover_color=style.HOVER,
            text_color=style.link_color(),
            font=style.fonts().small,
            command=lambda: self.app.open_help(CERTIFICATE_GUIDE_SECTION, source="enlace de Certificado digital"),
        )
        guide_link.grid(row=card.row(3), column=0, columnspan=3, sticky="w", padx=style.CARD_PAD - 6, pady=(6, 0))
        ToolTip(guide_link, tr("Abre la guía: certificados reales y de prueba, y cómo verificar la firma"))
        details = ctk.CTkFrame(card, fg_color="transparent")
        details.grid(row=card.row(4), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD, pady=(8, 0))
        details.grid_columnconfigure(1, weight=1)
        self.reason_var = tk.StringVar()
        self.location_var = tk.StringVar()
        for index, (label, variable) in enumerate(((tr("Motivo"), self.reason_var), (tr("Lugar"), self.location_var))):
            field_label(details, label).grid(row=index, column=0, sticky="w", padx=(0, 8), pady=4)
            ctk.CTkEntry(details, textvariable=variable, placeholder_text=tr("Opcional"), height=30).grid(
                row=index, column=1, sticky="ew", pady=4
            )
        self.visible = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            card,
            text=tr("Mostrar la firma en el documento"),
            variable=self.visible,
            font=style.fonts().body,
            command=self._on_visible_toggled,
        ).grid(row=card.row(5), column=0, columnspan=3, sticky="w", padx=style.CARD_PAD, pady=(10, 6))
        muted_label(
            card, tr("La contraseña del certificado se pide al firmar y nunca se guarda."), wraplength=290
        ).grid(row=card.row(6), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD)

    def _build_viewer(self) -> None:
        viewer = Card(self.body)
        viewer.grid(row=0, column=1, sticky="nsew", pady=(0, style.PAD))
        # Card reparte el ancho entre sus columnas; aqui el lienzo ocupa todo.
        viewer.grid_columnconfigure(0, weight=1, minsize=0)
        viewer.grid_columnconfigure(1, weight=0, minsize=0)
        viewer.grid_rowconfigure(2, weight=1)

        # Visor compartido (el mismo de la seccion Visor) en modo pagina unica;
        # la firma es una herramienta mas sobre la pagina.
        self.view = PageView(
            viewer,
            continuous=False,
            placeholder=PLACEHOLDER_EMPTY,
            on_empty_click=lambda: self.source_field.browse(),
            on_drop=self._on_drop,
        )
        self.viewer_toolbar = ViewerToolbar(viewer, self.view, page_entry=False, zoom_menu=False)
        self.viewer_toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 8))
        self.document_label = self.viewer_toolbar.center
        ctk.CTkFrame(viewer, height=1, corner_radius=0, fg_color=style.CARD_BORDER).grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=1
        )
        self.view.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=12, pady=12)
        self.view.set_tool(_SignatureTool(self))
        self.view.on_page_changed(self._on_view_page_changed)

    # * Estado del visor (nombres que usan las pruebas y la colocacion) -------

    @property
    def page_index(self) -> int:
        return self.view.current_page

    @property
    def scale(self) -> float:
        return self.view.scale

    @property
    def offset(self) -> tuple[float, float]:
        return self.view.page_origin(self.view.current_page) if self.view.layout else (0.0, 0.0)

    @property
    def page_rect(self) -> pymupdf.Rect:
        return self.view.page_rect(self.view.current_page) if self.view.sizes else pymupdf.Rect(0, 0, 0, 0)

    @property
    def canvas(self):
        return self.view.canvas

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
            self.run_button.configure(text=tr("Firmar digitalmente"))
        else:
            hide(self.certificate_card)
            self.signature_card.grid(row=2, **card_options)
            hide(self.signature_hint)
            self.all_pages_check.configure(state="normal")
            self.run_button.configure(text=tr("Firmar PDF"))
        self._schedule_overlay()

    def _overlay_visible(self) -> bool:
        if self.digital:
            return self.visible.get()
        return self.signature_image is not None

    # * Eventos de controles ---------------------------------------------------

    def _on_mode_selected(self, value: str) -> None:
        self.log("Tipo de firma: %s", "Firma digital" if value == DIGITAL else "Firma visual")
        self._apply_mode()

    def _on_all_pages_toggled(self) -> None:
        self.log("Firmar todas las paginas: %s", "si" if self.all_pages.get() else "no")
        self._schedule_overlay()

    def _on_visible_toggled(self) -> None:
        self.log("Firma digital visible: %s", "si" if self.visible.get() else "no")
        self._schedule_overlay()

    def _on_drop(self, files: list) -> None:
        if files:
            self.source_field.set(files[0])

    # * Documento -------------------------------------------------------------

    def _open_document(self, path: Path) -> None:
        self._close_document()
        source = self.resolved(path)
        if source is None:
            return
        password = self.passwords.get(source)
        retry = False
        while True:
            try:
                self.document = core.open_document(source, password)
                break
            except core.PasswordRequiredError as error:
                self.log(
                    "El documento %s pide contrasena%s", source.name, " (la anterior no era correcta)" if retry else ""
                )
                password = ask_password(self, source.name, retry=retry or isinstance(error, core.WrongPasswordError))
                retry = True
                if not password:
                    self.log("Apertura cancelada: no se ingreso la contrasena", documento=source.name)
                    self.view.set_placeholder(*PLACEHOLDER_LOCKED)
                    return
            except core.PdfManagementError as error:
                self.app.show_error(error)
                self.view.set_placeholder(*PLACEHOLDER_EMPTY)
                return
        if password:
            self.passwords[source] = password
        self.document_path = source
        self.view.set_placeholder(*PLACEHOLDER_EMPTY)
        self.view.set_document(self.document, page=self.document.page_count - 1)  # se abre en la ultima pagina
        self.document_label.configure(text=source.name)
        self.output_field.set(self.default_output(source, tr("firmado")), auto=True)
        self.page_var.set(str(self.page_index + 1))
        self._update_size_limits()
        if not self.x_var.get() or not self.y_var.get():
            self._place_default()
        self.log(
            "Documento abierto: %s",
            source.name,
            paginas=self.document.page_count,
            protegido=bool(password),
            pagina_mostrada=self.page_index + 1,
        )

    def _close_document(self) -> None:
        self.view.set_document(None)
        self.document_label.configure(text="")
        if self.document is not None:
            self.document.close()
        self.document = None
        self.document_path = None

    def close_source(self) -> None:
        """Cerrar el PDF a firmar: el visor queda vacio, listo para otro."""
        self._close_document()
        self.view.set_placeholder(*PLACEHOLDER_EMPTY)
        super().close_source()

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
        if name != self._logged_signature:
            self._logged_signature = name
            self.log("Firma seleccionada: %s", name)
        path = self.signature_paths.get(name)
        if path is None:
            self.signature_image = None
            self.image_aspect = None
            self._show_preview(None, tr("Sin firma seleccionada"))
            self._schedule_overlay()
            return
        try:
            self.signature_image = core.load_signature(path)
            self.image_aspect = core.image_aspect_ratio(self.signature_image)
        except (OSError, core.PdfManagementError) as error:
            self.log("No se pudo cargar la firma %s: %s", name, error)
            self.signature_image = None
            self.image_aspect = None
            self._show_preview(None, tr("No se pudo cargar la imagen"))
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
        self.log("Lienzo para dibujar firma abierto")
        SignaturePad(self, on_saved=self._on_signature_drawn)

    def _on_signature_drawn(self, path: Path) -> None:
        self.log("Firma dibujada y guardada: %s", path.name)
        self._refresh_signatures(select=path)

    def _import_signature(self) -> None:
        chosen = filedialog.askopenfilename(
            title=tr("Importar firma"),
            filetypes=((tr("Imágenes"), "*.png *.jpg *.jpeg"), ("PNG", "*.png"), ("JPG", "*.jpg *.jpeg")),
        )
        if chosen:

            def import_and_select() -> None:
                stored = signatures.import_signature(chosen)
                self.log("Firma importada: %s", Path(chosen).name, guardada_como=stored.name)
                self._refresh_signatures(select=stored)

            self.guard(import_and_select)
        else:
            self.log_debug("Importar firma: dialogo cancelado")

    def _delete_signature(self) -> None:
        name = self.signature_menu.get()
        path = self.signature_paths.get(name)
        if path is None:
            return
        confirmed = messagebox.askyesno(
            tr("Borrar firma"), tr("¿Desea borrar la firma «{nombre}»?", nombre=name), parent=self
        )
        self.log("Borrar firma %s: %s", name, "confirmado" if confirmed else "cancelado")
        if confirmed:
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
        rect = core.signature_rect(self.page_rect, core.SignaturePlacement(x=x, y=y, width=width), self.aspect_ratio)
        self.x_var.set(f"{rect.x0:.1f}")
        self.y_var.set(f"{rect.y0:.1f}")

    def _place_default(self) -> None:
        """Ubicacion inicial: esquina inferior derecha, con margen."""
        try:
            width = float(self.width_var.get())
        except ValueError:
            width = core.DEFAULT_SIGNATURE_WIDTH
        margin = 54
        self._set_position(
            self.page_rect.width - width - margin, self.page_rect.height - width * self.aspect_ratio - margin
        )

    def _to_page_point(self, event) -> tuple[float, float]:
        hit = self.view.event_to_page(event, clamp=True)
        return (hit.x, hit.y) if hit is not None else (0.0, 0.0)

    def on_pointer_press(self, event) -> None:
        if self.document is None:
            self.source_field.browse()
            return
        if not self._overlay_visible():
            message = (
                tr("Active «Mostrar la firma en el documento» para ubicarla.")
                if self.digital
                else tr("Seleccione, dibuje o importe una firma primero.")
            )
            messagebox.showinfo(tr("Firma"), message, parent=self)
            return
        x, y = self._to_page_point(event)
        rect = self._current_rect()
        corner = self._corner_at(x, y, rect)
        if corner is not None and rect is not None:
            # La esquina opuesta queda fija mientras se arrastra.
            self._resize_corner = corner
            self._interaction = "redimensionar"
            self._resize_anchor = (
                rect.x1 if "w" in corner else rect.x0,
                rect.y1 if "n" in corner else rect.y0,
            )
            return
        if rect is not None and rect.contains(pymupdf.Point(x, y)):
            self._drag_offset = (x - rect.x0, y - rect.y0)
            self._interaction = "mover"
            return
        self._interaction = "colocar"
        width = rect.width if rect is not None else core.DEFAULT_SIGNATURE_WIDTH
        height = rect.height if rect is not None else width * self.aspect_ratio
        self._drag_offset = (width / 2, height / 2)
        self._set_position(x - width / 2, y - height / 2)

    def on_pointer_drag(self, event) -> None:
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

    def on_pointer_release(self, _event) -> None:
        if self._interaction:
            self._log_placement(self._interaction)
        self._interaction = None
        self._drag_offset = None
        self._resize_corner = None

    def _log_placement(self, action: str) -> None:
        """Posicion y tamano de la firma tras una accion del usuario (modo detallado)."""
        placement = self._placement()
        if placement is not None:
            self.log_debug(
                "Firma %s",
                {"mover": "movida", "colocar": "colocada", "redimensionar": "redimensionada"}.get(action, action),
                pagina=placement.page_number,
                x=placement.x,
                y=placement.y,
                ancho=placement.width,
            )

    def on_pointer_motion(self, event) -> None:
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
            ("nw", (rect.x0, rect.y0)),
            ("ne", (rect.x1, rect.y0)),
            ("sw", (rect.x0, rect.y1)),
            ("se", (rect.x1, rect.y1)),
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
        current = self._current_rect()
        if current is None:
            return
        if corner is None or anchor is None:
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
        self._log_placement(f"redimensionada con boton {'+' if delta > 0 else '-'}")

    def _on_size_slider(self, value: float) -> None:
        if not self._syncing_size:
            self._apply_size(value)
            # El deslizador avisa en cada paso: se registra solo el valor final.
            if self._size_log_job:
                self.after_cancel(self._size_log_job)
            self._size_log_job = self.after(400, self._log_slider_size)

    def _log_slider_size(self) -> None:
        self._size_log_job = None
        self._log_placement("redimensionada con el deslizador")

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
        if self.document is not None:
            self.view.go_to(index)

    def _on_view_page_changed(self, page: int) -> None:
        if self.page_var.get() != str(page + 1):
            self.page_var.set(str(page + 1))
        self._update_size_limits()
        self.log_debug("Visor: pagina %d de %d", page + 1, self._page_count())

    def _on_page_typed(self) -> None:
        try:
            index = int(self.page_var.get()) - 1
        except ValueError:
            return
        if self.document is not None and index != self.page_index and 0 <= index < self._page_count():
            self.view.go_to(index)

    def _update_size_limits(self) -> None:
        """El deslizador de tamano llega hasta el ancho de la pagina actual."""
        if self.view.sizes:
            self.size_slider.configure(to=max(MIN_SIGNATURE_WIDTH + 10, min(SIZE_SLIDER_MAX, self.page_rect.width)))
            self._sync_size_slider()

    def _schedule_overlay(self) -> None:
        if not self._redraw_pending:
            self._redraw_pending = True
            self.after_idle(self._redraw_overlay)

    def _redraw_overlay(self) -> None:
        self._redraw_pending = False
        self.view.redraw_overlays()  # borra la capa y llama a _SignatureTool.draw

    def draw_overlay(self) -> None:
        """Dibuja la firma, su borde y las asas (el visor ya borro la capa anterior)."""
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
            image_height = round(height - caption_height)
            self._draw_caption(x0, y0 + height, width, caption_height)
        if self.signature_image is not None and image_height > 0:
            self._overlay_photo = ImageTk.PhotoImage(
                self.signature_image.resize((width, image_height), Image.Resampling.LANCZOS)
            )
            self.canvas.create_image(x0, y0, anchor="nw", image=self._overlay_photo, tags="overlay")
        accent = style.themed(style.accent_color())
        self.canvas.create_rectangle(
            x0 - 2,
            y0 - 2,
            x0 + width + 2,
            y0 + height + 2,
            outline=accent,
            dash=(4, 3),
            width=1.5,
            tags="overlay",
        )
        half = HANDLE_SIZE / 2
        for corner_x, corner_y in ((x0, y0), (x0 + width, y0), (x0, y0 + height), (x0 + width, y0 + height)):
            self.canvas.create_rectangle(
                corner_x - half,
                corner_y - half,
                corner_x + half,
                corner_y + half,
                fill="white",
                outline=accent,
                width=1.5,
                tags="overlay",
            )

    def _draw_caption(self, x0: float, bottom: float, width: int, height: float) -> None:
        """Vista previa de la leyenda de la firma digital (misma proporcion que en el PDF)."""
        lines = (tr("Firmado digitalmente por:"), self._certificate_holder, tr("Fecha: dd/mm/aaaa hh:mm:ss"))
        padding = height * 0.08
        longest = max(len(line) for line in lines)
        # Courier: cada caracter mide 0.6 veces el tamano de la fuente.
        size = min((height - 2 * padding) / (len(lines) * 1.2), (width - 2 * padding) / (longest * 0.6))
        if size < 3:
            return
        self.canvas.create_text(
            x0 + padding,
            bottom - padding,
            text="\n".join(lines),
            anchor="sw",
            justify="left",
            fill="#26263A",
            font=("Courier New", -int(size)),
            tags="overlay",
        )

    # * Accion ----------------------------------------------------------------

    def _sign(self) -> None:
        def start() -> None:
            if self.document_path is None:
                raise core.InvalidInputError(tr("Seleccione el PDF a firmar."))
            signature = self.signature_paths.get(self.signature_menu.get())
            if self.digital:
                self._sign_digital(signature)
                return
            if signature is None:
                raise core.InvalidInputError(tr("Seleccione, dibuje o importe una firma."))
            placement = self._placement()
            if placement is None:
                raise core.InvalidInputError(tr("Haga clic en la vista previa para ubicar la firma."))
            output = self.resolve_output(self.output_field)
            if output is None:
                return
            source = self.document_path
            description = (
                tr("Firmando todas las páginas")
                if placement.all_pages
                else tr("Firmando la página {numero}", numero=placement.page_number)
            )
            self.log(
                "Firma visual solicitada: %s",
                source.name,
                firma=signature.name,
                pagina=placement.page_number,
                todas=placement.all_pages,
                x=placement.x,
                y=placement.y,
                ancho=placement.width,
                salida=output,
            )
            self.run_task(
                description,
                tr("PDF firmado"),
                lambda passwords: core.sign_pdf_with_image(
                    source, output, signature, placement, password=passwords.get(source)
                ),
                button=self.run_button,
            )

        self.guard(start)

    def _sign_digital(self, signature: Path | None) -> None:
        certificate = self.resolved(self.certificate_field.path)
        if certificate is None:
            raise core.InvalidInputError(tr("Seleccione el certificado digital (.pfx o .p12)."))
        placement = None
        if self.visible.get():
            placement = self._placement()
            if placement is None:
                raise core.InvalidInputError(tr("Haga clic en la vista previa para ubicar la firma."))
        else:
            signature = None
        output = self.resolve_output(self.output_field)
        if output is None:
            return
        unlocked = self._unlock_certificate(certificate)
        if unlocked is None:
            self.log("Firma digital cancelada: no se ingreso la contrasena del certificado")
            return
        info, pfx_password = unlocked
        self.log(
            "Certificado abierto: %s",
            certificate.name,
            titular=info.subject,
            emisor=info.issuer,
            autofirmado=info.self_signed,
            vence=info.valid_until.date(),
        )
        self._certificate_holder = info.subject
        self._schedule_overlay()
        if info.self_signed and not messagebox.askyesno(
            tr("Certificado autofirmado"),
            tr(
                "El certificado de «{titular}» es autofirmado.\n\n"
                "La firma será válida, pero programas como Adobe Acrobat mostrarán la "
                "identidad del firmante como desconocida.\n\n¿Desea continuar?",
                titular=info.subject,
            ),
            parent=self,
        ):
            self.log("Firma digital cancelada: el usuario no acepto el certificado autofirmado")
            return
        source = self.document_path
        if source is None:
            return
        reason = self.reason_var.get().strip() or None
        location = self.location_var.get().strip() or None
        self.log(
            "Firma digital solicitada: %s",
            source.name,
            certificado=certificate.name,
            visible=placement is not None,
            pagina=placement.page_number if placement else "-",
            imagen=signature.name if signature else "-",
            motivo=reason or "-",
            lugar=location or "-",
            salida=output,
        )
        self.run_task(
            tr("Firmando digitalmente como {titular}", titular=info.subject),
            tr("PDF firmado digitalmente"),
            lambda passwords: core.sign_pdf_with_certificate(
                source,
                output,
                certificate,
                pfx_password,
                placement=placement,
                signature_image=signature,
                reason=reason,
                location=location,
                password=passwords.get(source),
            ),
            button=self.run_button,
        )

    def _unlock_certificate(self, certificate: Path) -> tuple[core.CertificateInfo, str] | None:
        """Pide la contrasena del certificado hasta que sea correcta. ``None`` si se cancela."""
        retry = False
        while True:
            self.log_debug("Se pide la contrasena del certificado %s", certificate.name)
            pfx_password = ask_certificate_password(self, certificate.name, retry=retry)
            if pfx_password is None:
                return None
            try:
                return core.load_certificate(certificate, pfx_password), pfx_password
            except core.WrongCertificatePasswordError:
                self.log("Contrasena del certificado incorrecta; se vuelve a pedir", certificado=certificate.name)
                retry = True
