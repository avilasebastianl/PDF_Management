"""
Panel lateral "Firmas" del visor: verifica las firmas digitales del archivo y
ofrece firmar el documento (lo envia a la seccion Firmar).
"""

from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from ...core.verify import BROKEN, MODIFIED, UNTRUSTED, VALID, SignatureReport
from ...i18n import tr, trn
from .. import style
from ..widgets import muted_label, secondary_button

# Estado -> (simbolo, color, titulo)
STATES = {
    VALID: ("✓", style.SUCCESS, tr("Válida")),
    UNTRUSTED: ("!", style.WARNING, tr("Identidad no verificada")),
    MODIFIED: ("!", style.WARNING, tr("Modificado después de firmar")),
    BROKEN: ("✕", style.DANGER, tr("No válida")),
}


class SignaturesPanel(ctk.CTkFrame):
    """Lista de firmas con su estado; botones para verificar de nuevo y para firmar."""

    def __init__(self, master, *, on_verify: Callable[[], None], on_sign: Callable[[], None]) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0)
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=8, pady=(0, 6))
        buttons.grid_columnconfigure((0, 1), weight=1, uniform="buttons")
        self.verify_button = secondary_button(buttons, tr("Verificar"), on_verify, "refresh", height=30)
        self.verify_button.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        self.sign_button = secondary_button(buttons, tr("Firmar..."), on_sign, "signature", height=30)
        self.sign_button.grid(row=0, column=1, sticky="ew", padx=(3, 0))
        self.status = muted_label(self, "", wraplength=236, justify="left")
        self.status.pack(fill="x", padx=10, pady=(0, 6))
        self.list = ctk.CTkScrollableFrame(self, fg_color="transparent", corner_radius=0)
        self.list.pack(fill="both", expand=True)
        self.reports: list[SignatureReport] = []
        self.show_message(tr("Abra un PDF para ver sus firmas digitales."))

    def show_message(self, text: str) -> None:
        self.reports = []
        self._clear()
        self.status.configure(text=text)

    def show_reports(self, reports: list[SignatureReport], note: str = "") -> None:
        self.reports = reports
        self._clear()
        if not reports:
            text = tr("Este documento no tiene firmas digitales. Use «Firmar...» para agregar una.")
        else:
            text = trn("{count} firma digital", "{count} firmas digitales", len(reports))
        self.status.configure(text=f"{text}\n{note}" if note else text)
        for report in reports:
            self._add_card(report)

    def _clear(self) -> None:
        for child in self.list.winfo_children():
            child.destroy()

    def _add_card(self, report: SignatureReport) -> None:
        symbol, color, title = STATES[report.state]
        card = ctk.CTkFrame(
            self.list, fg_color=style.ROW_BG, corner_radius=8, border_width=1, border_color=style.CARD_BORDER
        )
        card.pack(fill="x", padx=4, pady=(0, 6))
        card.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            card,
            text=symbol,
            width=26,
            height=26,
            corner_radius=13,
            fg_color=color,
            text_color="white",
            font=style.fonts().body_bold,
        ).grid(row=0, column=0, rowspan=2, sticky="n", padx=(10, 8), pady=10)
        ctk.CTkLabel(card, text=title, text_color=color, font=style.fonts().body_bold, anchor="w").grid(
            row=0, column=1, sticky="ew", padx=(0, 10), pady=(8, 0)
        )
        signer = report.signer or tr("Firmante desconocido")
        details = [signer]
        if report.signed_at is not None:
            details.append(report.signed_at.strftime("%d/%m/%Y %H:%M"))
        details.append(tr("Campo: {campo}", campo=report.field))
        muted_label(card, "\n".join(details), anchor="w", justify="left", wraplength=190).grid(
            row=1, column=1, sticky="ew", padx=(0, 10)
        )
        summary = report.error or report.summary
        ctk.CTkLabel(card, text=summary, font=style.fonts().small, anchor="w", justify="left", wraplength=220).grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(4, 10)
        )
