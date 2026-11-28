from __future__ import annotations

import asyncio


class EventHub:
    """Publica solo eventos nuevos a las conexiones activas."""

    def __init__(self, queue_size: int = 256) -> None:
        self._subscribers: set[asyncio.Queue[dict | None]] = set()
        self._queue_size = queue_size

    def subscribe(self) -> asyncio.Queue[dict | None]:
        queue: asyncio.Queue[dict | None] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict | None]) -> None:
        self._subscribers.discard(queue)

    async def publish(self, event: dict) -> None:
        for queue in tuple(self._subscribers):
            if queue.full():
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
                self.unsubscribe(queue)
                continue
            queue.put_nowait(event)
