"""How the API hands work to Celery. Kept behind a small interface so tests can record
enqueued tasks instead of needing a broker."""

import asyncio
from typing import Any, Protocol


class TaskQueue(Protocol):
    async def send(self, name: str, *args: Any) -> None: ...


class CeleryQueue:
    async def send(self, name: str, *args: Any) -> None:
        from app.workers.celery_app import celery_app  # imported lazily: reads settings

        # send_task does blocking broker I/O; keep it off the event loop.
        await asyncio.to_thread(celery_app.send_task, name, args=list(args))
