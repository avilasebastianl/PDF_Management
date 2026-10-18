# mypy: disable-error-code="misc"
# (self anotado como ViewerPage, su subclase: mypy lo marca, pero comprueba igual los atributos)
"""
Abrir, guardar (siempre Guardar como), propiedades, Enviar a y recientes.

Parte de ``ViewerPage`` (ver ``viewer.py``): los metodos anotan ``self`` con
``ViewerPage`` para que mypy compruebe los atributos que usan.
"""

from __future__ import annotations

import shutil
import tempfile
from functools import partial
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

from ... import core, recent
from ...core.create import create_document
from ...core.editing import DocumentSession
from ...i18n import tr, trn
from ..dialogs import DocumentPropertiesWindow, ask_password
from ..dropdown import set_dropdown_values
from ..new_document import ask_new_document
from .viewer_tabs import MAX_TABS, DocumentTab

if TYPE_CHECKING:
    from .viewer import ViewerPage


# Texto mostrado en "Enviar a" -> seccion de destino (su identificador, sin traducir).
SEND_TARGETS = {tr("Unir"): "Unir", tr("Extraer"): "Extraer", tr("Firmar"): "Firmar", tr("Proteger"): "Proteger"}
RECENT_PLACEHOLDER = tr("Recientes")
SEND_PLACEHOLDER = tr("Enviar a...")


class FilesMixin:
    """Abrir, guardar (siempre Guardar como), propiedades, Enviar a y recientes."""

    _exported_folder: Path | None  # copias temporales enviadas a Unir (se asigna en build)

    def browse(self: ViewerPage) -> None:
        chosen = filedialog.askopenfilename(title=tr("Abrir PDF"), filetypes=((tr("Archivos PDF"), "*.pdf"),))
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

    def merge_open_documents(self: ViewerPage) -> None:
        """
        Boton "Unir N PDFs": lleva los documentos abiertos, en el orden de las
        pestanas, a la seccion Unir. Los que tienen cambios sin guardar (o son
        nuevos) van como una copia temporal con esos cambios, sin guardarlos.
        """
        if len(self.tabs) < 2:
            return
        self.forget_exported_copies()  # las copias de una union anterior ya no hacen falta
        folder = Path(tempfile.mkdtemp(prefix="pdfmanagement_unir_"))
        self._exported_folder = folder
        paths: list[Path] = []
        passwords: dict[Path, str] = {}
        try:
            for tab in self.tabs:
                session = tab.session
                if session.modified or tab.temp_folder is not None:
                    paths.append(session.write_copy(core.unique_path(folder / tab.path.name)))
                    continue
                paths.append(tab.path)
                if session.password:
                    passwords[tab.path] = session.password
        except core.PdfManagementError as error:
            self.app.show_error(error)
            return
        self.log("Unir documentos abiertos", archivos=len(paths), copias=len(list(folder.iterdir())))
        self.app.show_page("Unir", source="boton Unir del Visor")
        self.app.pages["Unir"].load_files(paths, passwords, source="Visor")

    def forget_exported_copies(self: ViewerPage) -> None:
        folder = getattr(self, "_exported_folder", None)
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)
            self._exported_folder = None

    def new_document(self: ViewerPage) -> None:
        """Nuevo PDF en blanco o desde una plantilla, en una pestana nueva (Ctrl+N)."""
        spec = ask_new_document(self)
        if spec is None:
            self.log_debug("Nuevo PDF: cancelado")
            return
        folder = Path(tempfile.mkdtemp(prefix="pdfmanagement_nuevo_"))
        self._new_documents += 1
        number = f" {self._new_documents}" if self._new_documents > 1 else ""
        try:
            path = create_document(folder / f"{tr('Documento nuevo')}{number}.pdf", spec)
        except core.PdfManagementError as error:
            shutil.rmtree(folder, ignore_errors=True)
            self.app.show_error(error)
            return
        if not self.open_file(path, source="nuevo", remember=False):
            shutil.rmtree(folder, ignore_errors=True)
            return
        if self.tab is not None:
            self.tab.temp_folder = folder
        self.log("Nuevo PDF: %s", spec.template, tamano=spec.size, horizontal=spec.landscape, paginas=spec.pages)

    def open_file(self: ViewerPage, path: Path, source: str = "dialogo", remember: bool = True) -> bool:
        """
        Abre ``path`` en una pestana nueva (pide la contrasena si hace falta).
        Si ya esta abierto, muestra su pestana. ``remember=False`` no lo agrega
        a Recientes (documentos nuevos, que viven en una carpeta temporal).
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
                    trn(
                        "Puede tener hasta {count} documento abierto. Cierre alguna pestaña (Ctrl+W) para abrir otro.",
                        "Puede tener hasta {count} documentos abiertos. "
                        "Cierre alguna pestaña (Ctrl+W) para abrir otro.",
                        MAX_TABS,
                    )
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
        if remember:
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
        if self.tab is not None and self.tab.temp_folder is not None and self.saved_path is None:
            suggested = self.app.settings.output_path / self.session.path.name  # nuevo: sin "_editado"
        chosen = filedialog.asksaveasfilename(
            title=tr("Guardar como"),
            defaultextension=".pdf",
            filetypes=((tr("Archivos PDF"), "*.pdf"),),
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
        self.app.notify_success(tr("Documento guardado"), saved)
        return True

    def _confirm_discard(self: ViewerPage, action: str) -> bool:
        """
        Si hay cambios sin guardar pregunta: guardar como, descartar o cancelar.
        ``action`` ("cerrar la pestana" o "cerrar la aplicacion") elige la pregunta y va al registro.
        """
        session = self.session
        if session is None or not session.modified:
            return True
        questions = {
            "cerrar la pestana": tr("¿Desea guardarlos en un archivo nuevo antes de cerrar la pestaña?"),
            "cerrar la aplicacion": tr("¿Desea guardarlos en un archivo nuevo antes de cerrar la aplicación?"),
        }
        question = questions.get(action) or tr("¿Desea guardarlos en un archivo nuevo?")
        answer = messagebox.askyesnocancel(
            tr("Cambios sin guardar"),
            tr("{documento} tiene cambios sin guardar.", documento=session.name)
            + "\n\n"
            + question
            + "\n\n"
            + tr("Sí: Guardar como...\nNo: descartar los cambios\nCancelar: seguir editando"),
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
        section = SEND_TARGETS.get(target, target)  # tambien se admite el identificador de la seccion
        if session.modified:
            answer = messagebox.askyesnocancel(
                tr("Cambios sin guardar"),
                tr("Para enviar a {destino} la versión editada hay que guardarla primero.", destino=target)
                + "\n\n"
                + tr(
                    "Sí: Guardar como... y enviar la copia\nNo: enviar el último archivo guardado\nCancelar: no enviar"
                ),
                parent=self,
            )
            if answer is None or (answer and not self.save_as()):
                return
        path = self.saved_path or session.path
        self.log("Documento enviado a %s", section, archivo=path.name)
        self.app.open_in(section, path)

    def _recent_labels(self: ViewerPage) -> list[str]:
        labels = [entry.name for entry in self._recent]
        seen: dict[str, int] = {}
        for index, label in enumerate(labels):  # nombres repetidos: se agrega la carpeta
            if label in seen:
                labels[index] = f"{label}  ({self._recent[index].parent.name})"
            seen[label] = index
        return labels or [tr("(sin recientes)")]
