"""
Pagina "Convertir": documentos de Word y Excel a PDF.
"""

from pathlib import Path

from ... import core
from .. import style
from ..widgets import Card, FileField, muted_label, primary_button
from .base import BasePage

OFFICE_FILETYPES = (
    ("Documentos de Office", " ".join(f"*{ext}" for ext in core.OFFICE_EXTENSIONS)),
    ("Word", "*.docx *.doc *.rtf"),
    ("Excel", "*.xlsx *.xls"),
)


class ConvertPage(BasePage):
    name = "Convertir"
    title = "Convertir a PDF"
    subtitle = "Transforme documentos de Word y hojas de Excel en PDF con la calidad de Microsoft Office."
    icon_name = "convert"

    def build(self) -> None:
        source = Card(
            self.body,
            "Documento",
            "Formatos: " + ", ".join(core.OFFICE_EXTENSIONS) + "   ·   Requiere Microsoft Office instalado.",
        )
        source.grid(row=0, column=0, sticky="ew", pady=(0, style.GAP))
        self.source_field = FileField(
            source,
            source.row(0),
            "Archivo",
            filetypes=OFFICE_FILETYPES,
            on_change=self._on_source_selected,
            placeholder="Seleccione o arrastre un documento",
        )
        self.source_info = muted_label(source)
        self.source_info.grid(row=source.row(1), column=1, columnspan=2, sticky="ew", padx=(0, style.CARD_PAD))

        output = Card(self.body, "Resultado")
        output.grid(row=1, column=0, sticky="ew", pady=(0, style.GAP))
        self.output_field = FileField(
            output, output.row(0), "Guardar como", mode="save", initial_dir=lambda: self.app.settings.output_path
        )

        self.run_button = primary_button(self.body, "Convertir a PDF", self._convert, "convert", width=170)
        self.run_button.grid(row=2, column=0, sticky="e", pady=(4, style.PAD))

    def _on_source_selected(self, path: Path) -> None:
        if path.suffix.lower() not in core.OFFICE_EXTENSIONS:
            self.log("Formato no admitido: %s", path.name)
            self.source_info.configure(text="Formato no admitido.", text_color=style.DANGER)
            return
        self.log_debug("Documento listo para convertir: %s", path.name, formato=path.suffix.lower())
        self.source_info.configure(text="", text_color=style.TEXT_MUTED)
        self.output_field.set(self.default_output(path, ""), auto=True)

    def _convert(self) -> None:
        def start() -> None:
            source = self.resolved(self.source_field.path)
            if source is None:
                raise core.InvalidInputError("Seleccione el documento a convertir.")
            output = self.resolve_output(self.output_field)
            if output is None:
                return
            self.log("Convertir solicitado: %s", source.name, salida=output)
            self.run_task(
                f"Convirtiendo {source.name}",
                "Documento convertido",
                lambda _passwords: core.convert_to_pdf(source, output),
                button=self.run_button,
            )

        self.guard(start)
