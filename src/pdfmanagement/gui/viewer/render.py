"""
Dibujo de paginas con cola de prioridad y cache.

PyMuPDF no libera el GIL mientras dibuja (medido: un hilo dibujando bloquea la
interfaz ~16 ms por pagina) y no admite usar documentos desde varios hilos.
Por eso las paginas se dibujan en el hilo de la interfaz, **una por ciclo de
eventos**: entre pagina y pagina Tk atiende clics y desplazamiento, asi que la
ventana nunca queda bloqueada mas de lo que tarda una pagina (~10-40 ms).

- Los pedidos se ordenan por prioridad (las paginas mas cerca de la vista
  primero) y se descartan si dejan de ser utiles (zoom cambiado, documento
  cerrado).
- Las imagenes quedan en una cache LRU con limite de memoria; quien las
  muestra debe guardar su propia referencia (Tk borra la imagen si nadie la
  referencia).
- Con zoom alto el visor pide **mosaicos**: solo el trozo visible de la pagina
  (``clip``), asi una pagina al 400 % no genera una imagen de decenas de MB.
"""

import heapq
import itertools
import logging
import time
from collections import OrderedDict
from collections.abc import Callable

import pymupdf
from PIL import Image, ImageTk

logger = logging.getLogger(__name__)

DEFAULT_BUDGET_BYTES = 200 * 1024 * 1024
TICK_MS = 1

Tile = tuple[int, int] | None  # (columna, fila) del mosaico o None = pagina completa
RenderCallback = Callable[[int, float, ImageTk.PhotoImage, Tile], None]


def scale_key(scale: float) -> float:
    return round(scale, 3)


class RenderScheduler:
    """Cola de dibujo cooperativa (hilo de la interfaz) con cache de imagenes."""

    def __init__(self, widget, budget_bytes: int = DEFAULT_BUDGET_BYTES) -> None:
        self._widget = widget
        self._budget = budget_bytes
        self._document: pymupdf.Document | None = None
        self._generation = 0
        self._cache: OrderedDict[tuple[int, float, Tile], tuple[ImageTk.PhotoImage, int]] = OrderedDict()
        self._cache_bytes = 0
        self._queue: list[tuple[float, int, int, tuple[int, float, Tile]]] = []
        self._pending: dict[tuple[int, float, Tile], list[RenderCallback]] = {}
        self._clips: dict[tuple[int, float, Tile], pymupdf.Rect | None] = {}
        self._order = itertools.count()
        self._job: str | None = None
        self._paused = False
        self.rendered = 0  # paginas dibujadas (para mediciones)

    # * Documento -----------------------------------------------------------

    def set_document(self, document: pymupdf.Document | None) -> None:
        """Cambia el documento: vacia la cache y descarta los pedidos pendientes."""
        self._document = document
        self._generation += 1
        self.clear()

    def clear(self) -> None:
        self._cache.clear()
        self._cache_bytes = 0
        self._queue.clear()
        self._pending.clear()
        self._clips.clear()

    def invalidate(self, pages: set[int] | None = None) -> None:
        """Descarta imagenes de paginas editadas (o de todas)."""
        if pages is None:
            self.clear()
            return
        for key in [key for key in self._cache if key[0] in pages]:
            _photo, size = self._cache.pop(key)
            self._cache_bytes -= size

    # * Pedidos -------------------------------------------------------------

    def get(self, page: int, scale: float, tile: Tile = None) -> ImageTk.PhotoImage | None:
        key = (page, scale_key(scale), tile)
        entry = self._cache.get(key)
        if entry is None:
            return None
        self._cache.move_to_end(key)
        return entry[0]

    def request(self, page: int, scale: float, callback: RenderCallback, priority: float = 0.0,
                tile: Tile = None, clip: pymupdf.Rect | None = None) -> None:
        """
        Pide la pagina (o el mosaico ``tile`` recortado a ``clip``, en puntos
        de la pagina visible) a ``scale``. Si esta en cache se responde
        enseguida; si no, ``callback(page, scale, photo, tile)`` se invoca
        cuando se dibuje. Menor ``priority`` = antes.
        """
        key = (page, scale_key(scale), tile)
        cached = self.get(page, scale, tile)
        if cached is not None:
            callback(page, scale, cached, tile)
            return
        callbacks = self._pending.setdefault(key, [])
        if callback not in callbacks:
            callbacks.append(callback)
        self._clips[key] = clip
        heapq.heappush(self._queue, (priority, next(self._order), self._generation, key))
        self._schedule()

    def cancel_where(self, keep: Callable[[int, float, Tile], bool], callback: RenderCallback | None = None) -> None:
        """
        Descarta pedidos pendientes que ya no sirven (otra escala, fuera de la
        vista). Con ``callback`` solo se cancelan los pedidos de ese solicitante:
        el visor no debe borrar los de las miniaturas, que comparten la cola.
        """
        for key in list(self._pending):
            if keep(*key):
                continue
            callbacks = self._pending[key]
            if callback is not None:
                if callback not in callbacks:
                    continue
                callbacks.remove(callback)
                if callbacks:
                    continue
            del self._pending[key]
            self._clips.pop(key, None)

    # * Ciclo ---------------------------------------------------------------

    def drain(self, budget_ms: float = 150) -> None:
        """Dibuja ya los pedidos pendientes, hasta agotar ``budget_ms`` (antes de una animacion)."""
        deadline = time.perf_counter() + budget_ms / 1000
        while self._queue and time.perf_counter() < deadline:
            self._tick()
        if self._job is not None:
            self._widget.after_cancel(self._job)
            self._job = None
        self._schedule()

    def pause(self, paused: bool) -> None:
        """Detiene el dibujo (p. ej. durante una animacion); los pedidos esperan."""
        self._paused = paused
        if not paused and self._queue:
            self._schedule()

    def _schedule(self) -> None:
        if self._paused:
            return
        if self._job is None:
            self._job = self._widget.after(TICK_MS, self._tick)

    def _tick(self) -> None:
        self._job = None
        if self._paused:
            return
        while self._queue:
            _priority, _order, generation, key = heapq.heappop(self._queue)
            if generation != self._generation or key not in self._pending or self._document is None:
                continue  # pedido obsoleto
            callbacks = self._pending.pop(key)
            page, scale, tile = key
            photo = self._render(key, self._clips.pop(key, None))
            if photo is not None:
                for callback in callbacks:
                    callback(page, scale, photo, tile)
            break  # una imagen por ciclo: la interfaz responde entre medio
        if self._queue:
            self._schedule()

    def _render(self, key: tuple[int, float, Tile], clip: pymupdf.Rect | None) -> ImageTk.PhotoImage | None:
        page, scale, tile = key
        document = self._document
        if document is None or not 0 <= page < document.page_count:
            return None
        started = time.perf_counter()
        try:
            pixmap = document[page].get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=clip, alpha=False)
        except (RuntimeError, ValueError) as error:
            logger.warning("No se pudo dibujar la pagina %d: %s", page + 1, error)
            return None
        photo = ImageTk.PhotoImage(Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples))
        size = pixmap.width * pixmap.height * 4
        self._cache[key] = (photo, size)
        self._cache_bytes += size
        while self._cache_bytes > self._budget and len(self._cache) > 1:
            _key, (_photo, evicted) = self._cache.popitem(last=False)
            self._cache_bytes -= evicted
        self.rendered += 1
        logger.debug(
            "Pagina %d%s dibujada a escala %.2f en %.0f ms (%dx%d px, cache %.0f MB)",
            page + 1, f" mosaico {tile}" if tile else "", scale, (time.perf_counter() - started) * 1000,
            pixmap.width, pixmap.height, self._cache_bytes / 1_048_576,
        )
        return photo
