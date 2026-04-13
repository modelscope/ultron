# Copyright (c) ModelScope Contributors. All rights reserved.
import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, List, Optional

logger = logging.getLogger("ultron.async_queue")


@dataclass
class EmbeddingTask:
    """
    One embedding job submitted to EmbeddingQueue: text in, vector (or error) out.
    """
    task_id: str
    text: str
    callback: Optional[Callable] = None
    result: Optional[List[float]] = None
    error: Optional[str] = None
    done: bool = False
    _event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    async def wait(self, timeout: float = 30.0) -> Optional[List[float]]:
        """Block until the worker finishes or ``timeout`` elapses."""
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            self.error = "Embedding computation timed out"
        return self.result


class EmbeddingQueue:
    """
    Offloads embedding calls to a thread pool so the asyncio loop stays responsive.

    Heavy ``embed_text`` work runs via ``run_in_executor``; callers submit jobs and
    optionally await ``EmbeddingTask.wait()``.

    Usage:
        queue = EmbeddingQueue(embedding_service, max_size=100, workers=2)
        await queue.start()

        task = await queue.submit("some text")
        result = await task.wait()

        await queue.shutdown()
    """

    def __init__(
        self,
        embedding_service,
        max_size: int = 100,
        workers: int = 2,
    ):
        self.embedding = embedding_service
        self.max_size = max_size
        self.workers = workers
        self._queue: Optional[asyncio.Queue] = None
        self._executor = ThreadPoolExecutor(max_workers=workers)
        self._tasks: list = []
        self._running = False
        self._pending: dict = {}

    async def start(self) -> None:
        """Start background workers."""
        if self._running:
            return
        self._queue = asyncio.Queue(maxsize=self.max_size)
        self._running = True
        self._tasks = [
            asyncio.create_task(self._worker(i))
            for i in range(self.workers)
        ]
        logger.info("EmbeddingQueue started with %s workers", self.workers)

    async def shutdown(self) -> None:
        """Signal workers to stop and shut down the executor."""
        if not self._running:
            return
        self._running = False
        for _ in range(self.workers):
            await self._queue.put(None)
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._executor.shutdown(wait=False)
        logger.info("EmbeddingQueue shut down")

    async def submit(self, text: str, task_id: str = "") -> EmbeddingTask:
        """
        Enqueue text for embedding.

        Args:
            text: Input text for ``embedding_service.embed_text``.
            task_id: Optional id; if empty, a UUID is assigned.

        Returns:
            ``EmbeddingTask``; await ``task.wait()`` for the vector or timeout/error state.
        """
        if not self._running:
            raise RuntimeError("EmbeddingQueue not started")

        if not task_id:
            task_id = str(uuid.uuid4())

        task = EmbeddingTask(task_id=task_id, text=text)
        self._pending[task_id] = task
        await self._queue.put(task)
        return task

    async def _worker(self, worker_id: int) -> None:
        """Consumer loop: run ``embed_text`` in the thread pool and signal completion."""
        while self._running:
            try:
                task = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            if task is None:
                break

            try:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    self._executor,
                    self.embedding.embed_text,
                    task.text,
                )
                task.result = result
                task.done = True

                if task.callback:
                    try:
                        task.callback(task)
                    except Exception as e:
                        logger.warning(
                            "Callback error for task %s: %s", task.task_id, e,
                        )

            except Exception as e:
                task.error = str(e)
                logger.warning("Worker %s embedding error: %s", worker_id, e)

            finally:
                task._event.set()
                self._pending.pop(task.task_id, None)
                self._queue.task_done()

    @property
    def pending_count(self) -> int:
        """Number of tasks not yet finished (best-effort, includes in-flight)."""
        return len(self._pending)

    @property
    def is_running(self) -> bool:
        """True between ``start()`` and ``shutdown()``."""
        return self._running

    def get_stats(self) -> dict:
        """Queue snapshot for metrics or debugging."""
        return {
            "running": self._running,
            "workers": self.workers,
            "max_size": self.max_size,
            "pending_count": self.pending_count,
            "queue_size": self._queue.qsize() if self._queue else 0,
        }
