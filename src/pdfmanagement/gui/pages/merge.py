"""
Pagina "Unir": combina varios PDFs en el orden definido por el usuario.
"""

from pathlib import Path

import customtkinter as ctk

from ... import core
from .. import style
from ..icons import icon
from ..widgets import (
    Card,
    FileField,
    enable_file_drop,
    format_size,
    icon_button,
    muted_label,
    primary_button,
    secondary_button,
)
from .base import BasePage


class MergePage(BasePage):
    name = "Unir"
    title = "Unir PDFs"
    subtitle = "Combine varios documentos en un solo PDF. Arrastre archivos a la lista y ordenelos."
    icon_name = "merge"
    scrollable = False

    def build(self) -> None:
        self.files: list[core.PdfInfo] = []
        self.body.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(self.body, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, style.GAP))
        toolbar.grid_columnconfigure(3, weight=1)
        primary_button(toolbar, "Agregar PDFs", self._browse_files, "add").grid(row=0, column=0)
        secondary_button(toolbar, "Ordenar A-Z", self._sort_by_name, "sort").grid(row=0, column=1, padx=8)
        secondary_button(toolbar, "Vaciar lista", self._clear, "clear").grid(row=0, column=2)
        self.summary = muted_label(toolbar, anchor="e")
        self.summary.grid(row=0, column=3, sticky="e")

        self.list_frame = ctk.CTkScrollableFrame(
            self.body, corner_radius=style.CORNER, fg_color=style.CARD_BG,
            border_width=1, border_color=style.CARD_BORDER,
        )
        self.list_frame.grid(row=1, column=0, sticky="nsew")
        self.list_frame.grid_columnconfigure(0, weight=1)

        output = Card(self.body)
        output.grid(row=2, column=0, sticky="ew", pady=(style.GAP + 2, style.PAD))
        self.output_field = FileField(
            output, output.row(0), "Guardar como", mode="save", initial_dir=lambda: self.app.settings.output_path
        )
        options = ctk.CTkFrame(output, fg_color="transparent")
        options.grid(row=output.row(1), column=0, columnspan=3, sticky="ew", padx=style.CARD_PAD, pady=(4, 0))
        options.grid_columnconfigure(0, weight=1)
        self.bookmarks = ctk.CTkCheckBox(options, text="Crear un marcador por cada archivo", font=style.fonts().body)
        self.bookmarks.grid(row=0, column=0, sticky="w")
        self.run_button = primary_button(options, "Unir PDFs", self._merge, "merge", width=150)
        self.run_button.grid(row=0, column=1, sticky="e")

        enable_file_drop(self.list_frame, self._add_files)
        if hasattr(self.list_frame, "_parent_canvas"):
            enable_file_drop(self.list_frame._parent_canvas, self._add_files)  # noqa: SLF001
        self._reset_output()
        self._render()

    def on_show(self) -> None:
        if self.output_field.auto:
            self._reset_output()

    # * Acciones ------------------------------------------------------------

    def _browse_files(self) -> None:
        from tkinter import filedialog

        files = filedialog.askopenfilenames(title="Agregar PDFs", filetypes=(("Archivos PDF", "*.pdf"),))
        self._add_files([Path(file) for file in files])

    def _add_files(self, files: list[Path]) -> None:
        known = {info.path for info in self.files}
        rejected = []
        for file in files:
            if file.is_dir():
                files.extend(sorted(file.glob("*.pdf")))
                continue
            try:
                info = core.get_pdf_info(file)
            except core.PdfManagementError:
                rejected.append(file.name)
                continue
            if info.path not in known:
                self.files.append(info)
                known.add(info.path)
        self._render()
        if rejected:
            self.app.show_error(core.InvalidInputError("Se ignoraron archivos no validos:\n" + "\n".join(rejected)))

    def _move(self, index: int, offset: int) -> None:
        target = index + offset
        if 0 <= target < len(self.files):
            self.files[index], self.files[target] = self.files[target], self.files[index]
            self._render()

    def _remove(self, index: int) -> None:
        del self.files[index]
        self._render()

    def _sort_by_name(self) -> None:
        self.files.sort(key=lambda info: info.path.name.lower())
        self._render()

    def _clear(self) -> None:
        self.files.clear()
        self.passwords.clear()
        self._render()

    def _reset_output(self) -> None:
        self.output_field.set(core.unique_path(self.app.settings.output_path / "PDF_unido.pdf"), auto=True)

    def _merge(self) -> None:
        def start() -> None:
            if len(self.files) < 2:
                raise core.InvalidInputError("Agregue al menos dos PDFs para unir.")
            output = self.resolve_output(self.output_field)
            if output is None:
                return
            sources = [info.path for info in self.files]
            add_bookmarks = bool(self.bookmarks.get())
            self.run_task(
                "Uniendo PDFs",
                "PDF unido",
                lambda passwords: core.merge_pdfs(sources, output, passwords=passwords, add_bookmarks=add_bookmarks),
                button=self.run_button,
                on_success=lambda _result: self._reset_output() if self.output_field.auto else None,
            )

        self.guard(start)

    # * Render ----------------------------------------------------------------

    def _render(self) -> None:
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        if not self.files:
            self.summary.configure(text="")
            empty = ctk.CTkFrame(self.list_frame, fg_color="transparent")
            empty.grid(row=0, column=0, sticky="nsew", pady=80)
            ctk.CTkLabel(empty, text="", image=icon("pdf", 48, style.TEXT_MUTED)).pack()
            ctk.CTkLabel(empty, text="Arrastre aqui sus archivos PDF", font=style.fonts().section).pack(pady=(12, 2))
            muted_label(empty, "o use el boton \"Agregar PDFs\". Tambien puede soltar carpetas.").pack()
            enable_file_drop(empty, self._add_files)
            return

        total_pages = sum(info.page_count or 0 for info in self.files)
        total_size = sum(info.size_bytes for info in self.files)
        self.summary.configure(
            text=f"{len(self.files)} archivos  ·  {total_pages} paginas  ·  {format_size(total_size)}"
        )
        for index, info in enumerate(self.files):
            self._render_row(index, info)
        enable_file_drop(self.list_frame, self._add_files)

    def _render_row(self, index: int, info: core.PdfInfo) -> None:
        row = ctk.CTkFrame(self.list_frame, corner_radius=8, fg_color=style.ROW_BG)
        row.grid(row=index, column=0, sticky="ew", padx=6, pady=3)
        row.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            row, text=f"{index + 1}", width=28, height=28, corner_radius=14,
            fg_color=style.accent_color(), text_color=style.WHITE, font=style.fonts().small,
        ).grid(row=0, column=0, rowspan=2, padx=(12, 10), pady=10)
        ctk.CTkLabel(row, text="", image=icon("lock" if info.encrypted else "pdf", 20, style.TEXT_MUTED)).grid(
            row=0, column=1, rowspan=2, padx=(0, 10)
        )
        ctk.CTkLabel(row, text=info.path.name, font=style.fonts().body_bold, anchor="w").grid(
            row=0, column=2, sticky="ew", pady=(8, 0)
        )
        pages = f"{info.page_count} paginas" if info.page_count is not None else "protegido"
        muted_label(row, f"{pages}  ·  {format_size(info.size_bytes)}  ·  {info.path.parent}").grid(
            row=1, column=2, sticky="ew", pady=(0, 8)
        )

        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.grid(row=0, column=3, rowspan=2, padx=8)
        up = icon_button(actions, "up", lambda: self._move(index, -1), "Subir")
        down = icon_button(actions, "down", lambda: self._move(index, 1), "Bajar")
        remove = icon_button(actions, "delete", lambda: self._remove(index), "Quitar de la lista")
        up.pack(side="left")
        down.pack(side="left", padx=2)
        remove.pack(side="left")
        if index == 0:
            up.configure(state="disabled")
        if index == len(self.files) - 1:
            down.configure(state="disabled")
