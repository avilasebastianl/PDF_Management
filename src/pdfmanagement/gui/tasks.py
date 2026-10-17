"""
Ejecucion de operaciones en segundo plano sin bloquear la interfaz.

Tkinter no es seguro entre hilos: los trabajadores solo ejecutan la operacion y
el hilo principal consulta periodicamente los resultados para invocar los
callbacks. Asi ningun widget se toca fuera del hilo de la interfaz.

Cada tarea recibe un numero y queda en el registro su inicio, su duracion y su
resultado (o el tipo de error), lo que permite seguir operaciones concurrentes.
"""

import itertools
import logging
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import core
from .events import one_line

logger = logging.getLogger(__name__)

POLL_INTERVAL_MS = 80


@dataclass
class _Task:
    number: int
    description: str
    future: Future
    on_success: Callable[[Any], None]
    on_error: Callable[[BaseException], None]
    started: float = field(default_factory=time.perf_counter)


class TaskRunner:
    """Cola de tareas con un pool de hilos y notificacion de estado ocupado."""

    def __init__(self, root, on_busy_change: Callable[[bool, str], None], max_workers: int = 2) -> None:
        self._root = root
        self._on_busy_change = on_busy_change
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="pdf-task")
        self._tasks: list[_Task] = []
        self._polling = False
        self._numbers = itertools.count(1)

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
        number = next(self._numbers)
        future = self._executor.submit(operation)
        self._tasks.append(_Task(number, description, future, on_success, on_error))
        logger.info("Tarea #%d iniciada: %s (en curso: %d)", number, description, len(self._tasks))
        self._notify()
        if not self._polling:
            self._polling = True
            self._root.after(POLL_INTERVAL_MS, self._poll)

    def shutdown(self) -> None:
        """Cancela las tareas pendientes sin esperar a las que estan en curso."""
        if self._tasks:
            logger.warning(
                "Cierre con %d tarea(s) sin terminar: %s",
                len(self._tasks), ", ".join(f"#{task.number} {task.description}" for task in self._tasks),
            )
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _poll(self) -> None:
        finished = [task for task in self._tasks if task.future.done()]
        for task in finished:
            self._tasks.remove(task)
            self._notify()
            elapsed = time.perf_counter() - task.started
            try:
                result = task.future.result()
            except BaseException as error:  # noqa: BLE001 - se reporta al usuario
                expected = isinstance(error, core.PdfManagementError)
                logger.log(
                    logging.INFO if expected else logging.ERROR,
                    "Tarea #%d '%s' fallo en %.2f s: %s: %s",
                    task.number, task.description, elapsed, type(error).__name__, one_line(error),
                )
                task.on_error(error)
            else:
                summary = _summarize(result)
                logger.info("Tarea #%d '%s' terminada en %.2f s -> %s", task.number, task.description, elapsed, summary)
                task.on_success(result)

        if self._tasks:
            self._root.after(POLL_INTERVAL_MS, self._poll)
        else:
            self._polling = False

    def _notify(self) -> None:
        message = self._tasks[-1].description if self._tasks else ""
        self._on_busy_change(self.busy, message)


def _summarize(result: Any) -> str:
    """Resumen corto del resultado de una tarea para el registro."""
    if isinstance(result, Path):
        return result.name
    if isinstance(result, (dict, list, tuple, set)):
        return f"{len(result)} resultados"
    return type(result).__name__
