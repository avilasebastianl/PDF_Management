"""
Ejecucion de operaciones en segundo plano sin bloquear la interfaz.

Tkinter no es seguro entre hilos: los trabajadores solo ejecutan la operacion y
el hilo principal consulta periodicamente los resultados para invocar los
callbacks. Asi ningun widget se toca fuera del hilo de la interfaz.
"""

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

POLL_INTERVAL_MS = 80


@dataclass
class _Task:
    description: str
    future: Future
    on_success: Callable[[Any], None]
    on_error: Callable[[BaseException], None]


class TaskRunner:
    """Cola de tareas con un pool de hilos y notificacion de estado ocupado."""

    def __init__(self, root, on_busy_change: Callable[[bool, str], None], max_workers: int = 2) -> None:
        self._root = root
        self._on_busy_change = on_busy_change
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="pdf-task")
        self._tasks: list[_Task] = []
        self._polling = False

    @property
    def busy(self) -> bool:
        return bool(self._tasks)

    @property
    def pending(self) -> int:
        """Numero de tareas en curso o en cola."""
        return len(self._tasks)

    def submit(
        self,
        description: str,
        operation: Callable[[], Any],
        on_success: Callable[[Any], None],
        on_error: Callable[[BaseException], None],
    ) -> None:
        """Programa ``operation`` en un hilo; los callbacks corren en el hilo de la GUI."""
        logger.debug("Tarea iniciada: %s", description)
        future = self._executor.submit(operation)
        self._tasks.append(_Task(description, future, on_success, on_error))
        self._notify()
        if not self._polling:
            self._polling = True
            self._root.after(POLL_INTERVAL_MS, self._poll)

    def shutdown(self) -> None:
        """Cancela las tareas pendientes sin esperar a las que estan en curso."""
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _poll(self) -> None:
        finished = [task for task in self._tasks if task.future.done()]
        for task in finished:
            self._tasks.remove(task)
            self._notify()
            try:
                result = task.future.result()
            except BaseException as error:  # noqa: BLE001 - se reporta al usuario
                task.on_error(error)
            else:
                task.on_success(result)

        if self._tasks:
            self._root.after(POLL_INTERVAL_MS, self._poll)
        else:
            self._polling = False

    def _notify(self) -> None:
        message = self._tasks[-1].description if self._tasks else ""
        self._on_busy_change(self.busy, message)
