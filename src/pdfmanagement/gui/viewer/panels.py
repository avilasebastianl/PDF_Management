"""
Paneles laterales del visor: marcadores (indice), busqueda y anotaciones.

Usan ``tk.Listbox`` (con los colores del tema) en lugar de un widget de
CustomTkinter por fila: listas de miles de entradas siguen siendo instantaneas.
"""

from __future__ import annotations

import time
import tkinter as tk
from collections.abc import Callable, Iterator

import customtkinter as ctk
import pymupdf

from ...core.editing import AnnotationInfo, SearchHit, SearchOptions, iter_search
from ...i18n import tr, trn
from .. import style
from ..events import log_event
from ..widgets import icon_button, muted_label, secondary_button, set_enabled
from .page_view import PageView

SEARCH_BUDGET_MS = 15  # tiempo maximo de busqueda por ciclo de eventos
PUBLISH_EVERY_MS = 150  # cada cuanto se actualizan los resaltados mientras se busca
MAX_LISTED_RESULTS = 2000  # resultados en la lista (todos se resaltan igual)


class ThemedList(ctk.CTkFrame):
    """``tk.Listbox`` con barra de desplazamiento y colores del modo claro/oscuro."""

    def __init__(self, master, on_select: Callable[[int], None]) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.listbox = tk.Listbox(
            self,
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            font=(style.FONT_FAMILY, 10),
            exportselection=False,
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar = ctk.CTkScrollbar(self, orientation="vertical", command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        self._on_select_callback = on_select
        ctk.AppearanceModeTracker.add(self._apply_colors, self.listbox)
        self._apply_colors(ctk.get_appearance_mode())

    def _apply_colors(self, mode: str) -> None:
        dark = mode.lower() == "dark"

        def pick(pair):
            return pair[1] if dark else pair[0]

        self.listbox.configure(
            background=pick(style.CARD_BG),
            foreground=pick(style.TEXT),
            selectbackground=pick(style.accent_color()),
            selectforeground="white",
        )

    def _on_select(self, _event=None) -> None:
        selection = self.listbox.curselection()
        if selection:
            self._on_select_callback(selection[0])

    def set_items(self, items: list[str]) -> None:
        self.listbox.delete(0, "end")
        if items:
            self.listbox.insert("end", *items)

    def append(self, items: list[str]) -> None:
        if items:
            self.listbox.insert("end", *items)

    def select(self, index: int) -> None:
        self.listbox.selection_clear(0, "end")
        if 0 <= index < self.listbox.size():
            self.listbox.selection_set(index)
            self.listbox.see(index)


class OutlinePanel(ctk.CTkFrame):
    """Marcadores del documento; un clic lleva a su pagina."""

    def __init__(self, master, view: PageView) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.view = view
        self.entries: list[tuple[int, str, int]] = []
        self.list = ThemedList(self, self._go_to)
        self.empty = muted_label(self, tr("Este documento no tiene marcadores."), wraplength=200)
        self.set_entries([])

    def set_entries(self, entries: list[tuple[int, str, int]]) -> None:
        self.entries = entries
        if entries:
            self.empty.pack_forget()
            self.list.pack(fill="both", expand=True)
            self.list.set_items([f"{'    ' * (level - 1)}{title}" for level, title, _page in entries])
        else:
            self.list.pack_forget()
            self.empty.pack(fill="x", padx=12, pady=12)

    def _go_to(self, index: int) -> None:
        _level, title, page = self.entries[index]
        if page >= 1:
            log_event("Visor", "Marcador: %s", title, pagina=page)
            self.view.go_to(page - 1)


class AnnotationsPanel(ctk.CTkFrame):
    """Anotaciones del documento: ir a cada una, editar su texto o eliminarla."""

    def __init__(
        self,
        master,
        *,
        on_select: Callable[[AnnotationInfo], None],
        on_edit: Callable[[], None],
        on_delete: Callable[[], None],
    ) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.on_select = on_select
        self.annotations: list[AnnotationInfo] = []
        self.count = muted_label(self, "")
        self.count.pack(fill="x", padx=10, pady=(0, 4))
        self.list = ThemedList(self, self._selected)
        self.list.pack(fill="both", expand=True)
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=6, pady=(6, 0))
        self.edit_button = secondary_button(buttons, tr("Editar texto"), on_edit, "edit", width=118, height=30)
        self.edit_button.pack(side="left")
        self.delete_button = secondary_button(buttons, tr("Eliminar"), on_delete, "delete", width=100, height=30)
        self.delete_button.pack(side="left", padx=(6, 0))
        self.set_annotations([])

    def set_annotations(self, annotations: list[AnnotationInfo], selected: AnnotationInfo | None = None) -> None:
        self.annotations = annotations
        self.list.set_items([self._describe(info) for info in annotations])
        total = len(annotations)
        self.count.configure(
            text=tr("Sin anotaciones. Use la barra de anotación sobre el visor.")
            if not total
            else trn("{count} anotación · clic para ir", "{count} anotaciones · clic para ir", total)
        )
        self.show_selected(selected)

    def show_selected(self, selected: AnnotationInfo | None) -> None:
        index = next(
            (
                i
                for i, info in enumerate(self.annotations)
                if selected is not None and (info.page, info.xref) == (selected.page, selected.xref)
            ),
            None,
        )
        self.list.listbox.selection_clear(0, "end")
        if index is not None:
            self.list.listbox.selection_set(index)
            self.list.listbox.see(index)
        set_enabled_button(self.edit_button, selected is not None and selected.has_text)
        set_enabled_button(self.delete_button, selected is not None)

    @staticmethod
    def _describe(info: AnnotationInfo) -> str:
        content = " ".join(info.content.split())
        detail = f": {content[:48]}{'...' if len(content) > 48 else ''}" if content else ""
        return tr("p. {n}", n=info.page + 1) + f"  ·  {info.label}{detail}"

    def _selected(self, index: int) -> None:
        if 0 <= index < len(self.annotations):
            self.on_select(self.annotations[index])


def set_enabled_button(button: ctk.CTkButton, enabled: bool) -> None:
    state = "normal" if enabled else "disabled"
    if button.cget("state") != state:
        button.configure(state=state)


class SearchPanel(ctk.CTkFrame):
    """
    Busqueda incremental: recorre el documento por tramos sin bloquear la
    interfaz, muestra los resultados a medida que aparecen y resalta todos.
    """

    def __init__(self, master, view: PageView) -> None:
        super().__init__(master, fg_color="transparent", corner_radius=0)
        self.view = view
        self.document: pymupdf.Document | None = None
        self.hits: list[SearchHit] = []
        self.current = -1
        self._iterator: Iterator[tuple[int, list[SearchHit]]] | None = None
        self._scanned = 0
        self._job: str | None = None
        self._query = ""
        self.query = tk.StringVar()
        self.match_case = tk.BooleanVar(value=False)
        self.whole_words = tk.BooleanVar(value=False)
        self._listeners: list[Callable[[], None]] = []

        self.entry = ctk.CTkEntry(
            self, textvariable=self.query, placeholder_text=tr("Buscar en el documento"), height=32
        )
        self.entry.pack(fill="x", padx=8, pady=(8, 4))
        self.entry.bind("<Return>", lambda _e: self.start() if self.query.get().strip() != self._query else self.next())
        self.entry.bind("<Shift-Return>", lambda _e: self.previous())
        options = ctk.CTkFrame(self, fg_color="transparent")
        options.pack(fill="x", padx=8)
        for text, variable in (
            (tr("Distinguir mayúsculas"), self.match_case),
            (tr("Solo palabras completas"), self.whole_words),
        ):
            ctk.CTkCheckBox(
                options,
                text=text,
                variable=variable,
                font=style.fonts().small,
                checkbox_width=18,
                checkbox_height=18,
                command=lambda: self.start() if self._query else None,
            ).pack(anchor="w", pady=2)
        navigation = ctk.CTkFrame(self, fg_color="transparent")
        navigation.pack(fill="x", padx=8, pady=(6, 4))
        self.status = muted_label(navigation, "")
        self.status.pack(side="left", fill="x", expand=True)
        self.previous_button = icon_button(navigation, "up", self.previous, tr("Anterior (Mayús + F3)"), size=28)
        self.next_button = icon_button(navigation, "down", self.next, tr("Siguiente (F3)"), size=28)
        self.next_button.pack(side="right")
        self.previous_button.pack(side="right", padx=2)
        self.results = ThemedList(self, self._go_to_hit)
        self.results.pack(fill="both", expand=True, padx=(8, 0), pady=(2, 8))
        self._update_buttons()

    # * API -----------------------------------------------------------------

    def set_document(self, document: pymupdf.Document | None) -> None:
        self.cancel()
        self.document = document
        self.clear()

    def focus_entry(self) -> None:
        self.entry.focus_set()
        self.entry.select_range(0, "end")

    def add_listener(self, listener: Callable[[], None]) -> None:
        """Avisa de cada cambio (resultados, seleccion, estado); lo usa la barra flotante."""
        self._listeners.append(listener)

    @property
    def searching(self) -> bool:
        return self._iterator is not None

    @property
    def searched_query(self) -> str:
        """Texto de la ultima busqueda iniciada (normalizado)."""
        return self._query

    def start(self) -> None:
        """Inicia una busqueda nueva desde la pagina actual."""
        self.cancel()
        query = " ".join(self.query.get().split())
        self._query = query
        self.hits, self.current, self._scanned = [], -1, 0
        self.results.set_items([])
        self.view.set_search_hits({})
        if not query or self.document is None:
            self.status.configure(text="")
            self._update_buttons()
            return
        options = SearchOptions(match_case=self.match_case.get(), whole_words=self.whole_words.get())
        self._search_options = options
        self._started = time.perf_counter()
        self._published_at = 0.0
        self._iterator = iter_search(self.document, query, options, start_page=self.view.current_page)
        self._step()

    def cancel(self) -> None:
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
        self._iterator = None

    def clear(self) -> None:
        self.cancel()
        self.query.set("")
        self._query = ""
        self.hits, self.current = [], -1
        self.results.set_items([])
        self.status.configure(text="")
        self.view.set_search_hits({})
        self._update_buttons()

    def invalidate(self) -> None:
        """El documento cambio: los resultados ya no valen (se conserva el texto buscado)."""
        had_results = bool(self.hits) or self._iterator is not None
        self.cancel()
        self.hits, self.current = [], -1
        self.results.set_items([])
        self.view.set_search_hits({})
        self.status.configure(text=tr("El documento cambió: pulse Enter para buscar de nuevo") if had_results else "")
        self._update_buttons()

    def next(self) -> None:
        if self.hits:
            self._select((self.current + 1) % len(self.hits))

    def previous(self) -> None:
        if self.hits:
            self._select((self.current - 1) % len(self.hits))

    # * Busqueda por tramos -------------------------------------------------

    def _step(self) -> None:
        self._job = None
        if self._iterator is None or self.document is None:
            return
        deadline = time.perf_counter() + SEARCH_BUDGET_MS / 1000
        new_hits: list[SearchHit] = []
        finished = False
        while time.perf_counter() < deadline:
            try:
                _page, hits = next(self._iterator)
            except StopIteration:
                finished = True
                break
            self._scanned += 1
            new_hits.extend(hits)
        if new_hits:
            first_batch = not self.hits
            self.hits.extend(new_hits)
            room = MAX_LISTED_RESULTS - self.results.listbox.size()
            if room > 0:
                self.results.append([tr("Pág. {n}", n=hit.page + 1) + f"  ·  {hit.context}" for hit in new_hits[:room]])
            if first_batch:
                self._select(0)  # el primer resultado se muestra apenas aparece
        now = time.perf_counter()
        if self.hits and (finished or now - self._published_at > PUBLISH_EVERY_MS / 1000):
            # Redibujar todos los resaltados en cada tramo crece cuadraticamente: se limita.
            self._publish_hits()
            self._published_at = now
        total = self.document.page_count
        if finished:
            self._iterator = None
            elapsed = (time.perf_counter() - self._started) * 1000
            self.status.configure(text=self._count_text() if self.hits else tr("Sin resultados"))
            log_event(
                "Visor",
                "Busqueda: %s",
                self._query,
                resultados=len(self.hits),
                paginas=total,
                mayusculas=self._search_options.match_case,
                palabra_completa=self._search_options.whole_words,
                duracion=f"{elapsed:.0f} ms",
            )
        else:
            scanned = trn(
                "Buscando... {revisadas}/{count} página",
                "Buscando... {revisadas}/{count} páginas",
                total,
                revisadas=self._scanned,
            )
            found = trn("{count} resultado", "{count} resultados", len(self.hits))
            self.status.configure(text=f"{scanned} · {found}")
            self._job = self.after(1, self._step)
        self._update_buttons()

    def _publish_hits(self) -> None:
        by_page: dict[int, list[pymupdf.Rect]] = {}
        for hit in self.hits:
            by_page.setdefault(hit.page, []).extend(hit.rects)
        current = (
            (self.hits[self.current].page, self.hits[self.current].rects)
            if 0 <= self.current < len(self.hits)
            else None
        )
        self.view.set_search_hits(by_page, current)

    def _go_to_hit(self, index: int) -> None:
        self._select(index, from_list=True)

    def _select(self, index: int, from_list: bool = False) -> None:
        self.current = index
        hit = self.hits[index]
        if not from_list:
            self.results.select(index)
        page_hits = self.view.search_hits
        self.view.reveal(hit.page, hit.rects[0])
        self.view.set_search_hits(page_hits, (hit.page, hit.rects))
        if self._iterator is None:
            self.status.configure(text=self._count_text())
        self._update_buttons()

    def _count_text(self) -> str:
        if self.current >= 0:
            return tr("{actual} de {total}", actual=self.current + 1, total=len(self.hits))
        return trn("{count} resultado", "{count} resultados", len(self.hits))

    def _update_buttons(self) -> None:
        set_enabled(self.previous_button, len(self.hits) > 1)
        set_enabled(self.next_button, len(self.hits) > 1)
        for listener in self._listeners:
            listener()
