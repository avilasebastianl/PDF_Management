"""
Avisos de cambios de un documento abierto.

``DocumentSession`` anuncia cada cambio y quien muestra el documento (el
visor, sus miniaturas, el panel de anotaciones, una segunda vista) se
actualiza solo, en un unico lugar, en vez de que cada accion recuerde a mano
todo lo que hay que refrescar.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

STRUCTURE = "estructura"  # paginas giradas, movidas, insertadas, eliminadas (o deshacer/rehacer)
CONTENT = "contenido"  # solo cambio lo dibujado en ``pages`` (anotaciones, texto)
SAVED = "guardado"  # se guardo una copia: cambia el estado "sin guardar"


@dataclass(frozen=True)
class DocumentChange:
    kind: str
    label: str = ""
    pages: frozenset[int] = field(default_factory=frozenset)


Listener = Callable[[DocumentChange], None]


class ChangeNotifier:
    def __init__(self) -> None:
        self._listeners: list[Listener] = []

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Registra ``listener``; devuelve la funcion que lo da de baja."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    def emit(self, change: DocumentChange) -> None:
        for listener in list(self._listeners):
            listener(change)
