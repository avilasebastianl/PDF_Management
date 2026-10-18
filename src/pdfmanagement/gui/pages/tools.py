"""
Pagina "Herramientas": comprimir, dividir, numerar paginas y marca de agua.

Un mismo documento de origen y una pestana por herramienta; cada una escribe
un archivo nuevo (dividir: varios, en una carpeta) y nunca toca el original.
"""

import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from ... import core
from ...core import tools
from ...i18n import tr, trn
from .. import style
from ..dropdown import dropdown_menu
from ..finish_controls import PreviewPane, WatermarkControls
from ..widgets import Card, FileField, field_label, format_size, muted_label, primary_button, secondary_button
from .base import BasePage

COMPRESS, SPLIT, NUMBER, WATERMARK = tr("Comprimir"), tr("Dividir"), tr("Numerar páginas"), tr("Marca de agua")
TOOLS = (COMPRESS, SPLIT, NUMBER, WATERMARK)
LEVELS = {
    tr("Baja (sin perder calidad)"): "baja",
    tr("Media (recomendada)"): "media",
    tr("Alta (imágenes más livianas)"): "alta",
}
SPLIT_MODES = {tr("Por rangos"): "rangos", tr("Cada N páginas"): "cada", tr("Por marcadores"): "marcadores"}
POSITIONS = {
    tr("Abajo al centro"): "abajo-centro",
    tr("Abajo a la derecha"): "abajo-derecha",
    tr("Abajo a la izquierda"): "abajo-izquierda",
    tr("Arriba al centro"): "arriba-centro",
    tr("Arriba a la derecha"): "arriba-derecha",
    tr("Arriba a la izquierda"): "arriba-izquierda",
}
# Orientacion de la marca de agua -> angulo (grados, antihorario como se ve).
PREVIEW_HEIGHT = 440
PREVIEW_DELAY_MS = 250  # se espera a que deje de escribir antes de redibujar
SUFFIXES = {COMPRESS: tr("comprimido"), NUMBER: tr("numerado"), WATERMARK: tr("marca")}


class ToolsPage(BasePage):
    name = "Herramientas"
    title = tr("Herramientas")
    subtitle = tr("Comprima, divida, numere páginas o agregue una marca de agua. El original nunca se modifica.")
    icon_name = "tools"

    def build(self) -> None:
        self.page_count: int | None = None
        source = Card(self.body, tr("Documento de origen"))
        source.grid(row=0, column=0, sticky="ew", pady=(0, style.GAP))
        self.source_field = FileField(
            source,
            source.row(0),
            "PDF",
            on_change=self._on_source_selected,
            placeholder=tr("Seleccione o arrastre un PDF"),
            initial_dir=lambda: self.app.settings.output_path,
            on_clear=self.close_source,
        )
        self.source_info = muted_label(source)
        self.source_info.grid(row=source.row(1), column=1, columnspan=2, sticky="ew", padx=(0, style.CARD_PAD))

        self.tool = ctk.CTkSegmentedButton(self.body, values=list(TOOLS), command=self._show_tool, height=36)
        self.tool.set(COMPRESS)
        self.tool.grid(row=1, column=0, sticky="w", pady=(0, style.GAP))
        self.cards = {
            COMPRESS: self._build_compress(),
            SPLIT: self._build_split(),
            NUMBER: self._build_numbers(),
            WATERMARK: self._build_watermark(),
        }

        self.output_card = Card(self.body, tr("Resultado"))
        self.output_card.grid(row=3, column=0, sticky="ew", pady=(0, style.GAP))
        self.output_field = FileField(
            self.output_card,
            self.output_card.row(0),
            tr("Guardar como"),
            mode="save",
            initial_dir=lambda: self.app.settings.output_path,
        )
        self.folder_row = ctk.CTkFrame(self.output_card, fg_color="transparent")
        self.folder_row.grid_columnconfigure(1, weight=1)
        field_label(self.folder_row, tr("Carpeta")).grid(row=0, column=0, sticky="w", padx=(0, style.GAP))
        self.folder = tk.StringVar()
        ctk.CTkEntry(self.folder_row, textvariable=self.folder, height=34).grid(row=0, column=1, sticky="ew")
        secondary_button(self.folder_row, tr("Examinar"), self._choose_folder, "folder", width=110).grid(
            row=0, column=2, padx=(8, 0)
        )
        self.run_button = primary_button(self.body, COMPRESS, self._run, "tools", width=190)
        self.run_button.grid(row=4, column=0, sticky="e", pady=(4, style.PAD))
        self._show_tool(COMPRESS, log=False)

    # * Opciones de cada herramienta ------------------------------------------------

    def _card(self, title: str, description: str) -> Card:
        card = Card(self.body, title, description)
        card.grid(row=2, column=0, sticky="ew", pady=(0, style.GAP))
        return card

    def _row(self, card: Card, offset: int, label: str, widget) -> None:
        field_label(card, label).grid(
            row=card.row(offset), column=0, sticky="w", padx=(style.CARD_PAD, style.GAP), pady=8
        )
        widget.grid(row=card.row(offset), column=1, sticky="w", pady=8, padx=(0, style.CARD_PAD))

    def _build_compress(self) -> Card:
        card = self._card(
            COMPRESS,
            tr(
                "Reduce el tamaño quitando datos sin uso y, en los niveles media y alta, bajando la resolución "
                "de las imágenes grandes. Ideal para enviar por correo."
            ),
        )
        self.level = dropdown_menu(card, list(LEVELS), width=260)
        self.level.set(next(label for label, key in LEVELS.items() if key == "media"))
        self._row(card, 0, tr("Nivel"), self.level)
        return card

    def _build_split(self) -> Card:
        card = self._card(
            SPLIT,
            tr("Crea varios archivos en una carpeta: por rangos, cada cierta cantidad de páginas o por capítulos."),
        )
        self.split_mode = dropdown_menu(card, list(SPLIT_MODES), self._on_split_mode, width=220)
        self.split_mode.set(next(iter(SPLIT_MODES)))
        self._row(card, 0, tr("Cómo dividir"), self.split_mode)
        self.split_value = tk.StringVar(value="1-3; 4-")
        self.split_entry = ctk.CTkEntry(card, textvariable=self.split_value, width=260, height=34)
        self._row(card, 1, tr("Valor"), self.split_entry)
        self.split_hint = muted_label(card, "")
        self.split_hint.grid(row=card.row(2), column=1, sticky="w", padx=(0, style.CARD_PAD))
        self._on_split_mode(self.split_mode.get(), log=False)
        return card

    def _build_numbers(self) -> Card:
        card = self._card(
            NUMBER, tr("Escribe el número en cada página. Use {n} para el número y {total} para el total.")
        )
        self.template = tk.StringVar(value=tr("Página {n} de {total}"))
        self._row(card, 0, tr("Formato"), ctk.CTkEntry(card, textvariable=self.template, width=260, height=34))
        self.position = dropdown_menu(card, list(POSITIONS), width=220)
        self.position.set(next(iter(POSITIONS)))
        self._row(card, 1, tr("Posición"), self.position)
        self.start = tk.StringVar(value="1")
        self._row(card, 2, tr("Empezar en"), ctk.CTkEntry(card, textvariable=self.start, width=80, height=34))
        self.number_pages = tk.StringVar()
        entry = ctk.CTkEntry(card, textvariable=self.number_pages, width=260, height=34, placeholder_text=tr("Todas"))
        self._row(card, 3, tr("Páginas"), entry)
        return card

    def _build_watermark(self) -> Card:
        card = self._card(
            WATERMARK,
            tr(
                "Texto grande y semitransparente, por ejemplo CONFIDENCIAL o BORRADOR. A la derecha se ve cómo quedará."
            ),
        )
        # Controles a la izquierda y la vista previa, grande, a la derecha (los mismos que en Unir).
        self.watermark = WatermarkControls(card, on_change=self._schedule_preview)
        self.watermark.grid(row=card.row(0), column=0, columnspan=2, sticky="new", padx=style.CARD_PAD, pady=8)
        self.mark_text = self.watermark.mark_text
        self.opacity = self.watermark.opacity
        self.orientation = self.watermark.orientation
        self.behind = self.watermark.behind
        self.preview = PreviewPane(card, PREVIEW_HEIGHT, tr("Elija un PDF para ver la vista previa"))
        self.preview.grid(row=card.row(0), column=2, sticky="ne", padx=(style.GAP, style.CARD_PAD), pady=8)
        card.grid_columnconfigure(2, weight=0)
        self._preview_job: str | None = None
        return card

    # * Vista previa de la marca de agua ------------------------------------------

    @property
    def mark_angle(self) -> float:
        return self.watermark.angle

    @property
    def _preview_image(self):
        return self.preview.image

    def _schedule_preview(self) -> None:
        if not hasattr(self, "preview"):
            return
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(PREVIEW_DELAY_MS, self.refresh_preview)

    def refresh_preview(self) -> None:
        """Dibuja la primera pagina del PDF elegido con la marca como quedara."""
        self._preview_job = None
        source = self.resolved(self.source_field.path)
        if source is None:
            self.preview.set_message(tr("Elija un PDF para ver la vista previa"))
            return
        options = self.watermark.options()
        try:
            image = tools.watermark_preview(
                source,
                options.text,
                height=self.preview.pixel_height,
                opacity=options.opacity,
                angle=options.angle,
                behind=options.behind,
                password=self.passwords.get(source),
            )
        except core.PasswordRequiredError:
            self.preview.set_message(tr("PDF protegido: la vista previa aparece al ingresar la contraseña."))
            return
        except core.PdfManagementError as error:
            self.preview.set_message(str(error))
            return
        self.preview.set_image(image)

    # * Eventos -----------------------------------------------------------------------

    def _show_tool(self, name: str, log: bool = True) -> None:
        for tool_name, card in self.cards.items():
            if tool_name == name:
                card.grid()
            else:
                card.grid_remove()
        splitting = name == SPLIT
        if splitting:
            self.output_field.hide()
            self.folder_row.grid(
                row=self.output_card.row(0), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD, pady=8
            )
        else:
            self.folder_row.grid_remove()
            self.output_field.show()
        self.run_button.configure(text=name)
        self._suggest_output()
        if name == WATERMARK:
            self._schedule_preview()
        if log:
            self.log("Herramienta: %s", name)

    def _on_split_mode(self, label: str, log: bool = True) -> None:
        mode = SPLIT_MODES[label]
        hints = {
            "rangos": (tr("Grupos separados por punto y coma, por ejemplo 1-3; 4-6; 7-"), "1-3; 4-"),
            "cada": (tr("Cantidad de páginas por archivo"), "2"),
            "marcadores": (tr("Un archivo por cada marcador principal del documento"), ""),
        }
        hint, default = hints[mode]
        self.split_hint.configure(text=hint)
        self.split_entry.configure(state="disabled" if mode == "marcadores" else "normal")
        if (default and not self.split_value.get().strip()) or (
            mode == "cada" and not self.split_value.get().isdigit()
        ):
            self.split_value.set(default)
        if log:
            self.log_debug("Dividir: %s", mode)

    def _on_source_selected(self, path: Path) -> None:
        self.passwords.clear()
        try:
            info = core.get_pdf_info(path)
        except core.PdfManagementError as error:
            self.source_info.configure(text=str(error), text_color=style.DANGER)
            return
        self.page_count = info.page_count
        pages = (
            trn("{count} página", "{count} páginas", info.page_count)
            if info.page_count
            else tr("Protegido con contraseña")
        )
        self.source_info.configure(text=f"{pages}  ·  {format_size(info.size_bytes)}", text_color=style.TEXT_MUTED)
        self.log("Origen listo: %s", info.path.name, paginas=info.page_count or "?", protegido=info.encrypted)
        self._suggest_output()
        self._schedule_preview()

    def close_source(self) -> None:
        self.page_count = None
        super().close_source()
        self._schedule_preview()  # la vista previa de la marca de agua vuelve al mensaje inicial

    def _suggest_output(self) -> None:
        source = self.resolved(self.source_field.path)
        if source is None:
            return
        name = self.tool.get()
        if name == SPLIT:
            if not self.folder.get().strip():
                self.folder.set(str(self.app.settings.output_path / f"{source.stem}_{tr('partes')}"))
        elif self.output_field.auto or not self.output_field.path:
            self.output_field.set(self.default_output(source, SUFFIXES[name]), auto=True)

    def _choose_folder(self) -> None:
        chosen = filedialog.askdirectory(title=tr("Carpeta para los archivos"), mustexist=False)
        if chosen:
            self.folder.set(chosen)

    # * Ejecutar ------------------------------------------------------------------

    def _run(self) -> None:
        def start() -> None:
            source = self.resolved(self.source_field.path)
            if source is None:
                raise core.InvalidInputError(tr("Seleccione el PDF de origen."))
            name = self.tool.get()
            if name == SPLIT:
                self._run_split(source)
                return
            output = self.resolve_output(self.output_field)
            if output is None:
                return
            operations = {COMPRESS: self._compress, NUMBER: self._number, WATERMARK: self._watermark}
            operations[name](source, output)

        self.guard(start)

    def _compress(self, source: Path, output: Path) -> None:
        level = LEVELS[self.level.get()]
        self.log("Comprimir solicitado: %s", source.name, nivel=level, salida=output)
        result: list[tools.CompressionResult] = []

        def operation(passwords) -> Path:
            result.append(tools.compress_pdf(source, output, level, password=passwords.get(source)))
            return result[-1].path

        def done(_path: Path) -> None:
            info = result[-1]
            self.source_info.configure(
                text=tr(
                    "Antes {before}  →  ahora {after} ({percent} % menos)",
                    before=format_size(info.size_before),
                    after=format_size(info.size_after),
                    percent=round(info.saved_ratio * 100),
                ),
                text_color=style.SUCCESS,
            )

        self.run_task(
            tr("Comprimiendo {name}", name=source.name),
            tr("PDF comprimido"),
            operation,
            button=self.run_button,
            on_success=done,
        )

    def _number(self, source: Path, output: Path) -> None:
        try:
            start = int(self.start.get())
        except ValueError as error:
            raise core.InvalidInputError(tr("El número inicial debe ser un entero.")) from error
        template, position = self.template.get(), POSITIONS[self.position.get()]
        pages = self.number_pages.get().strip() or None
        self.log("Numerar paginas solicitado: %s", source.name, formato=template, posicion=position, desde=start)
        self.run_task(
            tr("Numerando {name}", name=source.name),
            tr("Páginas numeradas"),
            lambda passwords: tools.add_page_numbers(
                source,
                output,
                template=template,
                position=position,
                start=start,
                pages=pages,
                password=passwords.get(source),
            ),
            button=self.run_button,
        )

    def _watermark(self, source: Path, output: Path) -> None:
        text, opacity, behind = self.mark_text.get(), self.opacity.get() / 100, bool(self.behind.get())
        angle = self.mark_angle
        self.log(
            "Marca de agua solicitada: %s",
            source.name,
            texto=text,
            opacidad=round(opacity, 2),
            angulo=angle,
            detras=behind,
        )
        self.run_task(
            tr("Agregando marca de agua a {name}", name=source.name),
            tr("Marca de agua agregada"),
            lambda passwords: tools.add_watermark(
                source, output, text, opacity=opacity, angle=angle, behind=behind, password=passwords.get(source)
            ),
            button=self.run_button,
        )

    def _run_split(self, source: Path) -> None:
        folder_text = self.folder.get().strip()
        if not folder_text:
            raise core.InvalidInputError(tr("Elija la carpeta donde se guardarán los archivos."))
        folder = Path(folder_text)
        mode = SPLIT_MODES[self.split_mode.get()]
        value = self.split_value.get()
        self.log("Dividir solicitado: %s", source.name, modo=mode, valor=value, carpeta=folder)
        parts: list[Path] = []

        def operation(passwords) -> Path:
            parts.extend(tools.split_pdf(source, folder, mode, value, password=passwords.get(source)))
            return parts[0]

        def done(_path: Path) -> None:
            self.source_info.configure(
                text=trn(
                    "Se creó {count} archivo en {folder}",
                    "Se crearon {count} archivos en {folder}",
                    len(parts),
                    folder=folder.name,
                ),
                text_color=style.SUCCESS,
            )

        self.run_task(
            tr("Dividiendo {name}", name=source.name),
            tr("PDF dividido"),
            operation,
            button=self.run_button,
            on_success=done,
        )
