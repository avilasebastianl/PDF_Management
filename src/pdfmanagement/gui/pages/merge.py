"""
Pagina "Unir": combina varios PDFs en el orden definido por el usuario.

La lista esta optimizada para muchos archivos:

- Cada fila se crea una sola vez; mover, quitar u ordenar solo recoloca las
  filas afectadas en lugar de reconstruir la lista completa.
- Las filas nuevas se construyen por lotes entre ciclos de eventos, asi la
  ventana sigue respondiendo mientras se agregan decenas de archivos.
- Los metadatos (paginas, tamano, cifrado) se leen en un hilo y cada fila se
  completa cuando estan listos.
- Arrastrar y soltar se registra en el contenedor, no en cada widget: Windows
  entrega la operacion al primer ancestro registrado.
"""

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from ... import core
from ...core import finish
from ...core.finish import SignatureOptions, WatermarkOptions
from ...i18n import tr, trn
from .. import style
from ..events import describe_files
from ..finish_controls import SIGNATURE_PAGES, PreviewPane, SignatureControls, WatermarkControls
from ..icons import icon
from ..widgets import (
    Card,
    FileField,
    ToolTip,
    enable_file_drop,
    format_size,
    hide,
    icon_button,
    muted_label,
    primary_button,
    secondary_button,
    set_enabled,
    show,
)
from .base import BasePage

BOOKMARKS_HELP = tr(
    "Marcador por cada archivo\n"
    "El PDF unido tendrá un marcador (el índice lateral que muestran los lectores de PDF) "
    "por cada archivo de origen, con su nombre. Así puede saltar directo al inicio de cada "
    "documento dentro del PDF final. Los marcadores que ya traían los PDFs se conservan, "
    "anidados dentro del marcador de su archivo.\n"
    "Si lo deja desactivado, el resultado conserva solo los marcadores originales."
)
PREVIEW_HEIGHT = 470
PREVIEW_DELAY_MS = 300  # se espera a que deje de cambiar opciones antes de redibujar
SIGNATURE_PAGE_FIRST = next(label for label, key in SIGNATURE_PAGES.items() if key == "primera")
ROWS_PER_BATCH = 3  # filas construidas por ciclo (~50 ms cada una en CustomTkinter)
DESTROY_PER_BATCH = 10  # filas destruidas por ciclo al vaciar la lista


@dataclass(eq=False)
class _Entry:
    """Archivo de la lista. ``info`` es ``None`` mientras se lee en segundo plano."""

    path: Path
    info: core.PdfInfo | None = None
    row: "_FileRow | None" = field(default=None, repr=False)


class _FileRow:
    """Fila visual de un archivo; se reutiliza al reordenar."""

    def __init__(self, page: "MergePage", entry: _Entry, index: int, total: int) -> None:
        # Los widgets se crean con su estado final: cada configure posterior
        # obliga a CustomTkinter a redibujar.
        self.entry = entry
        self._index: int | None = index
        self._edges = (index == 0, index == total - 1)

        self.frame = ctk.CTkFrame(page.list_frame, corner_radius=8, fg_color=style.ROW_BG)
        self.frame.grid_columnconfigure(2, weight=1)
        self.badge = ctk.CTkLabel(
            self.frame,
            text=str(index + 1),
            width=28,
            height=28,
            corner_radius=14,
            fg_color=style.accent_color(),
            text_color=style.ON_ACCENT,
            font=style.fonts().small,
        )
        self.badge.grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=10)
        self.kind = ctk.CTkLabel(self.frame, text="", image=icon("pdf", 20, style.TEXT_MUTED))
        self.kind.grid(row=0, column=1, rowspan=2, padx=(0, 10))
        ctk.CTkLabel(self.frame, text=entry.path.name, font=style.fonts().body_bold, anchor="w").grid(
            row=0, column=2, sticky="ew", pady=(8, 0)
        )
        self.meta = muted_label(self.frame, tr("Leyendo...  ·  {carpeta}", carpeta=entry.path.parent))
        self.meta.grid(row=1, column=2, sticky="ew", pady=(0, 8))

        actions = ctk.CTkFrame(self.frame, fg_color="transparent")
        actions.grid(row=0, column=3, rowspan=2, padx=8)
        self.up = icon_button(
            actions,
            "up",
            lambda: page.move_entry(entry, -1),
            tr("Subir"),
            state="disabled" if self._edges[0] else "normal",
        )
        self.down = icon_button(
            actions,
            "down",
            lambda: page.move_entry(entry, 1),
            tr("Bajar"),
            state="disabled" if self._edges[1] else "normal",
        )
        remove = icon_button(actions, "delete", lambda: page.remove_entry(entry), tr("Quitar de la lista"))
        self.up.pack(side="left")
        self.down.pack(side="left", padx=2)
        remove.pack(side="left")
        if entry.info is not None:
            self.update_info(entry.info)
        self.frame.grid(row=index, column=0, sticky="ew", padx=6, pady=3)

    def place_at(self, index: int, total: int) -> None:
        """Ubica la fila en la posicion ``index``; solo actualiza lo que cambio."""
        if index != self._index:
            self.frame.grid(row=index, column=0, sticky="ew", padx=6, pady=3)
            self.badge.configure(text=str(index + 1))
            self._index = index
        edges = (index == 0, index == total - 1)
        if edges != self._edges:
            set_enabled(self.up, not edges[0])
            set_enabled(self.down, not edges[1])
            self._edges = edges

    def update_info(self, info: core.PdfInfo) -> None:
        pages = (
            trn("{count} página", "{count} páginas", info.page_count)
            if info.page_count is not None
            else tr("protegido")
        )
        self.meta.configure(text=f"{pages}  ·  {format_size(info.size_bytes)}  ·  {info.path.parent}")
        self.kind.configure(image=icon("lock" if info.encrypted else "pdf", 20, style.TEXT_MUTED))

    def forget(self) -> None:
        self.frame.grid_forget()
        self._index = None


class MergePage(BasePage):
    name = "Unir"
    title = tr("Unir PDFs")
    subtitle = tr("Combine varios documentos en un solo PDF. Arrastre archivos a la lista y ordénelos.")
    icon_name = "merge"

    def _on_bookmarks_toggled(self) -> None:
        self.log("Marcador por archivo: %s", "activado" if self.bookmarks.get() else "desactivado")

    def build(self) -> None:
        self.entries: list[_Entry] = []
        self._rows_to_build: deque[_Entry] = deque()
        self._rows_to_destroy: deque[_FileRow] = deque()
        self._building = False
        self._preview_job: str | None = None

        toolbar = ctk.CTkFrame(self.body, fg_color="transparent")
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, style.GAP))
        toolbar.grid_columnconfigure(3, weight=1)
        primary_button(toolbar, tr("Agregar PDFs"), self._browse_files, "add").grid(row=0, column=0)
        secondary_button(toolbar, tr("Ordenar A-Z"), self._sort_by_name, "sort").grid(row=0, column=1, padx=8)
        secondary_button(toolbar, tr("Vaciar lista"), self._clear, "clear").grid(row=0, column=2)
        self.summary = muted_label(toolbar, anchor="e")
        self.summary.grid(row=0, column=3, sticky="e")

        # Una sola barra de desplazamiento (la de la seccion): la lista crece con los archivos.
        self.list_frame = ctk.CTkFrame(
            self.body,
            corner_radius=style.CORNER,
            fg_color=style.CARD_BG,
            border_width=1,
            border_color=style.CARD_BORDER,
        )
        self.list_frame.grid(row=1, column=0, sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)
        self._build_empty_state()

        self._build_finish_card()
        self._build_preview_card()

        output = Card(self.body)
        output.grid(row=3, column=0, sticky="ew", pady=(style.GAP, style.PAD))
        self.output_field = FileField(
            output, output.row(0), tr("Guardar como"), mode="save", initial_dir=lambda: self.app.settings.output_path
        )
        options = ctk.CTkFrame(output, fg_color="transparent")
        options.grid(row=output.row(1), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD, pady=(4, 0))
        options.grid_columnconfigure(0, weight=1)
        self.bookmarks = ctk.CTkCheckBox(
            options,
            text=tr("Crear un marcador por cada archivo"),
            font=style.fonts().body,
            command=self._on_bookmarks_toggled,
        )
        self.bookmarks.grid(row=0, column=0, sticky="w")
        ToolTip(self.bookmarks, BOOKMARKS_HELP, above=True)  # la casilla esta al pie de la seccion
        self.sign_button = secondary_button(options, tr("Unir y firmar..."), self._merge_and_sign, "sign", width=150)
        self.sign_button.grid(row=0, column=1, sticky="e", padx=(0, 8))
        ToolTip(self.sign_button, tr("Une los PDFs y abre el resultado en Firmar para ubicar la firma"), above=True)
        self.run_button = primary_button(options, tr("Unir PDFs"), self._merge, "merge", width=150)
        self.run_button.grid(row=0, column=2, sticky="e")

        # Contenedores registrados una sola vez; las filas heredan el destino.
        enable_file_drop(self.list_frame, self._add_files, recursive=False)
        canvas = getattr(self.list_frame, "_parent_canvas", None)
        if canvas is not None:
            enable_file_drop(canvas, self._add_files, recursive=False)
        enable_file_drop(self.empty_state, self._add_files)
        self._reset_output()
        self._refresh_summary()

    def _build_finish_card(self) -> None:
        """Marca de agua y firma del resultado (la vista previa esta en su propia columna)."""
        card = Card(
            self.body,
            tr("Marca de agua y firma (opcional)"),
            tr("Se aplican al PDF unido. La vista previa muestra cómo quedará."),
        )
        card.grid(row=2, column=0, sticky="ew", pady=(style.GAP + 2, 0))
        left = ctk.CTkFrame(card, fg_color="transparent")
        left.grid(row=card.row(0), column=0, columnspan=2, sticky="new", padx=style.CARD_PAD, pady=8)
        left.grid_columnconfigure(0, weight=1)
        self.add_watermark = ctk.CTkSwitch(
            left, text=tr("Agregar marca de agua"), font=style.fonts().body_bold, command=self._on_finish_toggled
        )
        self.add_watermark.grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.watermark = WatermarkControls(left, on_change=self._schedule_preview)
        self.add_signature = ctk.CTkSwitch(
            left, text=tr("Firmar el resultado"), font=style.fonts().body_bold, command=self._on_finish_toggled
        )
        self.add_signature.grid(row=2, column=0, sticky="w", pady=(12, 4))
        self.signature = SignatureControls(left, on_change=self._on_signature_changed)

    def _build_preview_card(self) -> None:
        """Vista previa del resultado: todas sus paginas, con la marca de agua y la firma elegidas."""
        card = Card(self.body, tr("Vista previa del resultado"))
        card.grid(row=1, column=1, rowspan=3, sticky="n", padx=(style.GAP, 0))
        self.preview = PreviewPane(card, PREVIEW_HEIGHT, tr("Agregue PDFs para ver la vista previa"))
        self.preview.grid(row=card.row(0), column=0, columnspan=3, padx=style.CARD_PAD, pady=(8, 4))
        navigation = ctk.CTkFrame(card, fg_color="transparent")
        navigation.grid(row=card.row(1), column=0, columnspan=3, pady=(0, 2))
        self.preview_previous = icon_button(
            navigation, "previous", lambda: self.step_preview(-1), tr("Página anterior del resultado")
        )
        self.preview_previous.pack(side="left")
        self.preview_label = ctk.CTkLabel(navigation, text="", width=130, font=style.fonts().body)
        self.preview_label.pack(side="left", padx=4)
        self.preview_next = icon_button(
            navigation, "next", lambda: self.step_preview(1), tr("Página siguiente del resultado")
        )
        self.preview_next.pack(side="left")
        self.preview_source = muted_label(card, "", anchor="center", wraplength=round(PREVIEW_HEIGHT * 0.72))
        self.preview_source.grid(row=card.row(2), column=0, columnspan=3, padx=style.CARD_PAD, pady=(0, 4))
        self.preview_index = 0
        self._on_finish_toggled(log=False)

    def _on_finish_toggled(self, log: bool = True) -> None:
        if self.add_watermark.get():
            self.watermark.grid(row=1, column=0, sticky="ew")
        else:
            self.watermark.grid_remove()
        if self.add_signature.get():
            self.signature.reload_library()  # pudo agregarse una firma en Firmar
            self.signature.grid(row=3, column=0, sticky="ew")
            self._show_signature_page()
        else:
            self.signature.grid_remove()
        if log:
            self.log(
                "Terminacion del PDF unido",
                marca_de_agua=bool(self.add_watermark.get()),
                firma=bool(self.add_signature.get()),
            )
        self._schedule_preview()

    def _finish_options(self, *, for_preview: bool = False) -> tuple[WatermarkOptions | None, SignatureOptions | None]:
        watermark = self.watermark.options() if self.add_watermark.get() else None
        signature = self.signature.options(for_preview=for_preview) if self.add_signature.get() else None
        return watermark, signature

    # * Vista previa navegable ------------------------------------------------------

    def _page_map(self) -> list[tuple[_Entry, int]]:
        """Cada archivo con sus paginas (1 mientras se lee o si esta protegido)."""
        return [(entry, max(1, (entry.info.page_count or 1) if entry.info else 1)) for entry in self.entries]

    @property
    def preview_total(self) -> int:
        return sum(count for _entry, count in self._page_map())

    def go_to_preview_page(self, index: int) -> None:
        """Pagina ``index`` del resultado (negativo: desde el final)."""
        total = self.preview_total
        if total:
            self.preview_index = max(0, min(index + total if index < 0 else index, total - 1))
        self._schedule_preview(delay=0)

    def step_preview(self, step: int) -> None:
        self.go_to_preview_page(self.preview_index + step)

    def _on_signature_changed(self) -> None:
        self._show_signature_page()
        self._schedule_preview()

    def _show_signature_page(self) -> None:
        """Al elegir la firma se muestra la pagina donde ira."""
        if self.add_signature.get() and self.entries:
            first = self.signature.pages.get() == SIGNATURE_PAGE_FIRST
            self.preview_index = 0 if first else self.preview_total - 1

    def _schedule_preview(self, delay: int = PREVIEW_DELAY_MS) -> None:
        if not hasattr(self, "preview_label"):
            return
        if self._preview_job is not None:
            self.after_cancel(self._preview_job)
        self._preview_job = self.after(delay, self.refresh_preview)

    def refresh_preview(self) -> None:
        """La pagina elegida del resultado con la marca de agua y la firma (si va en ella)."""
        self._preview_job = None
        pages = self._page_map()
        total = sum(count for _entry, count in pages)
        set_enabled(self.preview_previous, total > 0 and self.preview_index > 0)
        set_enabled(self.preview_next, total > 0 and self.preview_index < total - 1)
        if not total:
            self.preview_label.configure(text="")
            self.preview_source.configure(text="")
            self.preview.set_message(tr("Agregue PDFs para ver la vista previa"))
            return
        self.preview_index = min(self.preview_index, total - 1)
        index, local = self.preview_index, self.preview_index
        entry = pages[-1][0]
        for candidate, count in pages:  # archivo y pagina dentro de el
            if local < count:
                entry = candidate
                break
            local -= count
        self.preview_label.configure(text=tr("Página {n} de {total}", n=index + 1, total=total))
        self.preview_source.configure(text=f"{entry.path.name}  ·  " + tr("página {n}", n=local + 1))
        watermark, signature = self._finish_options(for_preview=True)
        if signature is not None:
            here = {"todas": True, "primera": index == 0, "ultima": index == total - 1}[signature.pages]
            if not here:
                signature = None
        try:
            image = finish.preview(
                entry.path,
                local,
                watermark=watermark,
                signature=signature,
                height=self.preview.pixel_height,
                password=self.passwords.get(entry.path),
            )
        except core.PasswordRequiredError:
            self.preview.set_message(tr("PDF protegido: la vista previa aparece al ingresar la contraseña."))
            return
        except core.PdfManagementError as error:
            self.preview.set_message(str(error))
            return
        self.preview.set_image(image)

    def _build_empty_state(self) -> None:
        self.empty_state = ctk.CTkFrame(self.list_frame, fg_color="transparent")
        ctk.CTkLabel(self.empty_state, text="", image=icon("pdf", 48, style.TEXT_MUTED)).pack()
        ctk.CTkLabel(self.empty_state, text=tr("Arrastre aquí sus archivos PDF"), font=style.fonts().section).pack(
            pady=(12, 2)
        )
        muted_label(self.empty_state, tr('o use el botón "Agregar PDFs". También puede soltar carpetas.')).pack()
        self.empty_state.grid(row=0, column=0, sticky="nsew", pady=80)

    def on_show(self) -> None:
        if self.output_field.auto:
            self._reset_output()

    @property
    def files(self) -> list[Path]:
        """Rutas en el orden actual de la lista."""
        return [entry.path for entry in self.entries]

    # * Agregar -------------------------------------------------------------

    def _browse_files(self) -> None:
        files = filedialog.askopenfilenames(title=tr("Agregar PDFs"), filetypes=((tr("Archivos PDF"), "*.pdf"),))
        self._add_files([Path(file) for file in files])

    def _add_files(self, files: Iterable[Path]) -> None:
        """Agrega rutas (o carpetas) al final de la lista sin bloquear la interfaz."""
        known = {entry.path for entry in self.entries}
        new_entries: list[_Entry] = []
        rejected: list[str] = []
        duplicated = 0
        for path in self._expand(files):
            if path.suffix.lower() != ".pdf" or not path.is_file():
                rejected.append(path.name)
                continue
            if path in known:
                duplicated += 1
                continue
            known.add(path)
            new_entries.append(_Entry(path))
        if new_entries:
            self.log(
                "Agregados %d archivos: %s",
                len(new_entries),
                describe_files(entry.path for entry in new_entries),
                total=len(self.entries) + len(new_entries),
            )
            previous_last = len(self.entries) - 1
            self.entries.extend(new_entries)
            if previous_last >= 0:
                self._place_rows(previous_last, previous_last + 1)  # ya no es la ultima fila
            self._rows_to_build.extend(new_entries)
            self._schedule_row_building()
            self._refresh_summary()
            paths = [entry.path for entry in new_entries]
            self.app.runner.submit(
                trn("Leyendo {count} PDF", "Leyendo {count} PDFs", len(paths)),
                lambda: _read_infos(paths),
                self._on_infos_read,
                self.app.show_error,
            )
        if duplicated:
            self.log_debug("Archivos ya presentes en la lista: %d (no se duplican)", duplicated)
        if rejected:
            self.log("Ignorados %d archivos no validos: %s", len(rejected), describe_files(rejected))
            self.app.show_error(
                core.InvalidInputError(tr("Se ignoraron archivos no válidos:") + "\n" + "\n".join(rejected))
            )

    @staticmethod
    def _expand(files: Iterable[Path]) -> list[Path]:
        expanded: list[Path] = []
        for file in files:
            path = Path(file).expanduser().resolve()
            if path.is_dir():
                expanded.extend(sorted(child.resolve() for child in path.glob("*.pdf")))
            else:
                expanded.append(path)
        return expanded

    def _on_infos_read(self, results: dict[Path, "core.PdfInfo | core.PdfManagementError"]) -> None:
        rejected = []
        for entry in list(self.entries):
            result = results.get(entry.path)
            if result is None:
                continue
            if isinstance(result, core.PdfInfo):
                entry.info = result
                if entry.row is not None:
                    entry.row.update_info(result)
            else:
                rejected.append(f"{entry.path.name}: {result}")
                self.remove_entry(entry, reason=f"no se pudo leer ({result})")
        self._refresh_summary()
        valid = [result for result in results.values() if isinstance(result, core.PdfInfo)]
        self.log_debug(
            "Metadatos leidos: %d PDFs",
            len(valid),
            paginas=sum(info.page_count or 0 for info in valid),
            protegidos=sum(1 for info in valid if info.encrypted),
        )
        if rejected:
            self.app.show_error(
                core.InvalidInputError(tr("Se quitaron archivos no válidos:") + "\n" + "\n".join(rejected))
            )

    # * Construccion por lotes ------------------------------------------------

    def _schedule_row_building(self) -> None:
        if not self._building:
            self._building = True
            self.after_idle(self._build_rows_batch)

    def _build_rows_batch(self) -> None:
        total = len(self.entries)
        for _ in range(min(ROWS_PER_BATCH, len(self._rows_to_build))):
            entry = self._rows_to_build.popleft()
            if entry not in self.entries:
                continue
            entry.row = _FileRow(self, entry, self.entries.index(entry), total)
        self._toggle_empty_state()
        if self._rows_to_build:
            self.after(1, self._build_rows_batch)
        else:
            self._building = False

    # * Reordenar y quitar ----------------------------------------------------

    def move_entry(self, entry: _Entry, offset: int) -> None:
        index = self.entries.index(entry)
        target = index + offset
        if not 0 <= target < len(self.entries):
            return
        self.entries[index], self.entries[target] = self.entries[target], self.entries[index]
        self._place_rows(min(index, target), max(index, target) + 1)
        self.log("Movido %s: posicion %d -> %d", entry.path.name, index + 1, target + 1)

    def _move(self, index: int, offset: int) -> None:
        """Compatibilidad: mueve por posicion."""
        if 0 <= index < len(self.entries):
            self.move_entry(self.entries[index], offset)

    def remove_entry(self, entry: _Entry, reason: str = "por el usuario") -> None:
        if entry not in self.entries:
            return
        index = self.entries.index(entry)
        self.log("Quitado %s (posicion %d) %s", entry.path.name, index + 1, reason, quedan=len(self.entries) - 1)
        self.entries.remove(entry)
        self.passwords.pop(entry.path, None)
        if entry.row is not None:
            entry.row.frame.destroy()
            entry.row = None
        # Las filas siguientes suben un lugar; la anterior puede pasar a ser la ultima.
        self._place_rows(max(index - 1, 0), len(self.entries))
        self._toggle_empty_state()
        self._refresh_summary()

    def _sort_by_name(self) -> None:
        self.log("Lista ordenada A-Z", archivos=len(self.entries))
        self.entries.sort(key=lambda entry: entry.path.name.lower())
        self._place_rows(0, len(self.entries))

    def load_files(self, paths: list[Path], passwords: dict[Path, str] | None = None, source: str = "Visor") -> None:
        """Reemplaza la lista por ``paths`` (p. ej. los documentos abiertos en el Visor)."""
        if self.entries:
            self._clear()
        self.passwords.update(passwords or {})
        self.preview_index = 0
        self.log("Archivos recibidos de %s", source, archivos=len(paths))
        self._add_files(paths)

    def receive_file(self, path: Path) -> None:
        self.log("Archivo recibido de otra seccion: %s", path.name)
        self._add_files([path])

    def _clear(self) -> None:
        self.log("Lista vaciada", archivos=len(self.entries))
        for entry in self.entries:
            if entry.row is not None:
                entry.row.forget()
                self._rows_to_destroy.append(entry.row)
                entry.row = None
        self.entries.clear()
        self._rows_to_build.clear()
        self.passwords.clear()
        self._toggle_empty_state()
        self._refresh_summary()
        self.after_idle(self._destroy_rows_batch)

    def _destroy_rows_batch(self) -> None:
        """Destruye filas ocultas por lotes para que vaciar la lista sea instantaneo."""
        for _ in range(min(DESTROY_PER_BATCH, len(self._rows_to_destroy))):
            self._rows_to_destroy.popleft().frame.destroy()
        if self._rows_to_destroy:
            self.after(1, self._destroy_rows_batch)

    def _place_rows(self, start: int, stop: int) -> None:
        total = len(self.entries)
        for index in range(start, min(stop, total)):
            row = self.entries[index].row
            if row is not None:
                row.place_at(index, total)

    # * Estado ----------------------------------------------------------------

    def _toggle_empty_state(self) -> None:
        if self.entries:
            hide(self.empty_state)
        else:
            show(self.empty_state)

    def _refresh_summary(self) -> None:
        self._schedule_preview()  # la primera o la ultima pagina pudieron cambiar
        if not self.entries:
            self.summary.configure(text="")
            return
        infos = [entry.info for entry in self.entries if entry.info is not None]
        pending = len(self.entries) - len(infos)
        text = "  ·  ".join(
            (
                trn("{count} archivo", "{count} archivos", len(self.entries)),
                trn("{count} página", "{count} páginas", sum(info.page_count or 0 for info in infos)),
                format_size(sum(info.size_bytes for info in infos)),
            )
        )
        if pending:
            text += "  ·  " + tr("leyendo {count}...", count=pending)
        self.summary.configure(text=text)

    # * Accion ----------------------------------------------------------------

    def _reset_output(self) -> None:
        self.output_field.set(core.unique_path(self.app.settings.output_path / (tr("PDF_unido") + ".pdf")), auto=True)

    def _merged(self, result: Path, then_sign: bool) -> None:
        if self.output_field.auto:
            self._reset_output()
        if then_sign:
            self.log("PDF unido enviado a Firmar", archivo=result.name)
            self.app.open_in("Firmar", result)

    def _merge_and_sign(self) -> None:
        """Une y abre el resultado en Firmar (para ubicar la firma a mano o firmar con certificado)."""
        self._merge(then_sign=True)

    def _merge(self, then_sign: bool = False) -> None:
        def start() -> None:
            if len(self.entries) < 2:
                raise core.InvalidInputError(tr("Agregue al menos dos PDFs para unir."))
            output = self.resolve_output(self.output_field)
            if output is None:
                return
            sources = self.files
            add_bookmarks = bool(self.bookmarks.get())
            watermark, signature = self._finish_options()  # valida antes de empezar (firma, certificado)
            self.log(
                "Unir PDFs solicitado: %s",
                describe_files(sources, limit=10),
                archivos=len(sources),
                marcadores=add_bookmarks,
                salida=output,
            )

            def operation(passwords) -> Path:
                merged = core.merge_pdfs(sources, output, passwords=passwords, add_bookmarks=add_bookmarks)
                return finish.apply_finish(merged, watermark=watermark, signature=signature)

            self.run_task(
                tr("Uniendo PDFs"),
                tr("PDF unido"),
                operation,
                button=self.run_button,
                on_success=lambda result: self._merged(result, then_sign),
            )

        self.guard(start)


def _read_infos(paths: list[Path]) -> dict[Path, "core.PdfInfo | core.PdfManagementError"]:
    """Lee los metadatos de cada PDF (se ejecuta en un hilo trabajador)."""
    results: dict[Path, core.PdfInfo | core.PdfManagementError] = {}
    for path in paths:
        try:
            results[path] = core.get_pdf_info(path)
        except core.PdfManagementError as error:
            results[path] = error
    return results
