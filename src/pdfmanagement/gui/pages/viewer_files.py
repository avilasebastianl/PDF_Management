# mypy: disable-error-code="misc"
# (self anotado como ViewerPage, su subclase: mypy lo marca, pero comprueba igual los atributos)
"""
Abrir, guardar (siempre Guardar como), propiedades, Enviar a y recientes.

Parte de ``ViewerPage`` (ver ``viewer.py``): los metodos anotan ``self`` con
``ViewerPage`` para que mypy compruebe los atributos que usan.
"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

from ... import core, recent
from ...core.editing import DocumentSession
from ..dialogs import DocumentPropertiesWindow, ask_password
from ..dropdown import set_dropdown_values
from .viewer_tabs import MAX_TABS, DocumentTab

if TYPE_CHECKING:
    from .viewer import ViewerPage


SEND_TARGETS = ("Unir", "Extraer", "Firmar", "Proteger")
RECENT_PLACEHOLDER = "Recientes"
SEND_PLACEHOLDER = "Enviar a..."


class FilesMixin:
    """Abrir, guardar (siempre Guardar como), propiedades, Enviar a y recientes."""

    def browse(self: ViewerPage) -> None:
        chosen = filedialog.askopenfilename(title="Abrir PDF", filetypes=(("Archivos PDF", "*.pdf"),))
        if chosen:
            self.open_file(Path(chosen), source="dialogo")
        else:
            self.log_debug("Abrir: dialogo cancelado")

    def receive_file(self: ViewerPage, path: Path) -> None:
        self.open_file(path, source="enviado desde otra seccion")

    def _on_drop(self: ViewerPage, files: list) -> None:
        if files:
            self.open_file(Path(files[0]), source="arrastrado")

    def _open_recent(self: ViewerPage, label: str) -> None:
        self.recent_menu.set(RECENT_PLACEHOLDER)
        labels = self._recent_labels()
        if label in labels and self._recent:
            self.open_file(self._recent[labels.index(label)], source="recientes")

    def open_file(self: ViewerPage, path: Path, source: str = "dialogo") -> bool:
        """
        Abre ``path`` en una pestana nueva (pide la contrasena si hace falta).
        Si ya esta abierto, muestra su pestana.
        """
        path = Path(path)
        existing = self._find_tab(path)
        if existing is not None:
            self.switch_to(existing)
            self.log("Documento ya abierto: se muestra su pestana", archivo=path.name, origen=source)
            return True
        if len(self.tabs) >= MAX_TABS:
            self.app.show_error(
                core.InvalidInputError(
                    f"Puede tener hasta {MAX_TABS} documentos abiertos. Cierre alguna pestana (Ctrl+W) para abrir otro."
                )
            )
            return False
        password = self._ask_password_until_valid(path)
        if password is False or password is True:
            return False
        try:
            session = DocumentSession.open(path, password)
        except core.PdfManagementError as error:
            self.app.show_error(error)
            return False
        tab = DocumentTab(session)
        tab.unsubscribe = session.changes.subscribe(partial(self._on_document_changed, tab))
        self.tabs.append(tab)
        self.switch_to(len(self.tabs) - 1)
        self._recent = recent.add_recent(session.path)
        set_dropdown_values(self.recent_menu, self._recent_labels())
        self.recent_menu.set(RECENT_PLACEHOLDER)
        self._refresh_file_state()
        self.log(
            "Documento abierto: %s",
            session.name,
            origen=source,
            paginas=session.page_count,
            protegido=session.encrypted,
            firmas_digitales=session.has_signatures(),
            marcadores=len(session.table_of_contents()),
            pestanas=len(self.tabs),
        )
        return True

    def _ask_password_until_valid(self: ViewerPage, path: Path) -> str | bool | None:
        """
        Comprueba si ``path`` necesita contrasena y la pide hasta que sea
        correcta. Devuelve la contrasena (``None`` si no hace falta) o
        ``False`` si el usuario cancela o el archivo no se puede leer.
        """
        password, retry = None, False
        while True:
            try:
                core.open_document(path, password).close()
                return password
            except core.PasswordRequiredError as error:
                self.log("%s pide contrasena%s", path.name, " (la anterior no era correcta)" if retry else "")
                password = ask_password(self, path.name, retry=retry or isinstance(error, core.WrongPasswordError))
                retry = True
                if not password:
                    self.log("Cancelado: no se ingreso la contrasena", archivo=path.name)
                    return False
            except core.PdfManagementError as error:
                self.app.show_error(error)
                return False

    def save_as(self: ViewerPage) -> bool:
        """Guarda una copia con el dialogo "Guardar como" (nunca sobre el original)."""
        if self.session is None:
            return False
        suggested = self.saved_path or self.default_output(self.session.path, "editado")
        chosen = filedialog.asksaveasfilename(
            title="Guardar como",
            defaultextension=".pdf",
            filetypes=(("Archivos PDF", "*.pdf"),),
            initialdir=str(suggested.parent),
            initialfile=suggested.name,
            parent=self,
        )
        if not chosen:
            self.log_debug("Guardar como: dialogo cancelado")
            return False
        return self.save_to(Path(chosen))

    def save_to(self: ViewerPage, output: Path) -> bool:
        session = self.session
        if session is None:
            return False
        try:
            saved = session.save_as(output)
        except core.PdfManagementError as error:
            self.app.show_error(error)
            return False
        if self.tab is not None:
            self.tab.saved_path = saved
        self._refresh_file_state()
        self.log(
            "Documento guardado como: %s",
            saved.name,
            carpeta=saved.parent,
            paginas=session.page_count,
            protegido=bool(session.password),
        )
        self.app.notify_success("Documento guardado", saved)
        return True

    def _confirm_discard(self: ViewerPage, action: str) -> bool:
        """Si hay cambios sin guardar pregunta: guardar como, descartar o cancelar."""
        session = self.session
        if session is None or not session.modified:
            return True
        answer = messagebox.askyesnocancel(
            "Cambios sin guardar",
            f"{session.name} tiene cambios sin guardar.\n\n"
            f"Desea guardarlos en un archivo nuevo antes de {action}?\n\n"
            "Si: Guardar como...\nNo: descartar los cambios\nCancelar: seguir editando",
            icon="warning",
            parent=self,
        )
        decision = {True: "guardar", False: "descartar", None: "cancelar"}[answer]
        self.log("Cambios sin guardar antes de %s: %s", action, decision, archivo=session.name)
        if answer is None:
            return False
        return self.save_as() if answer else True

    def show_properties(self: ViewerPage) -> None:
        if self.session is None:
            return
        self.log("Propiedades abiertas", archivo=self.session.name)
        size = self.view.sizes[self.view.current_page] if self.view.sizes else None
        DocumentPropertiesWindow(self, self.session.properties(), size)

    def _send_to(self: ViewerPage, target: str) -> None:
        self.send_menu.set(SEND_PLACEHOLDER)
        session = self.session
        if session is None:
            return
        if session.modified:
            answer = messagebox.askyesnocancel(
                "Cambios sin guardar",
                f"Para enviar a {target} la version editada hay que guardarla primero.\n\n"
                "Si: Guardar como... y enviar la copia\nNo: enviar el ultimo archivo guardado\nCancelar: no enviar",
                parent=self,
            )
            if answer is None or (answer and not self.save_as()):
                return
        path = self.saved_path or session.path
        self.log("Documento enviado a %s", target, archivo=path.name)
        self.app.open_in(target, path)

    def _recent_labels(self: ViewerPage) -> list[str]:
        labels = [entry.name for entry in self._recent]
        seen: dict[str, int] = {}
        for index, label in enumerate(labels):  # nombres repetidos: se agrega la carpeta
            if label in seen:
                labels[index] = f"{label}  ({self._recent[index].parent.name})"
            seen[label] = index
        return labels or ["(sin recientes)"]
