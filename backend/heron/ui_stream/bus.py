import asyncio

from heron.ui_stream.events import BuildEvent


class BuildEventBus:
    """Holds one event queue per in-flight build so SSE clients can subscribe."""

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = {}

    def create(self, build_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues[build_id] = queue
        return queue

    def get(self, build_id: str) -> asyncio.Queue | None:
        return self._queues.get(build_id)

    async def publish(self, build_id: str, event: BuildEvent) -> None:
        queue = self._queues.get(build_id)
        if queue is not None:
            await queue.put(event)

    def remove(self, build_id: str) -> None:
        self._queues.pop(build_id, None)


bus = BuildEventBus()
