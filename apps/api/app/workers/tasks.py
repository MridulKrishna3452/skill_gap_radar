"""Celery tasks. P0 has only a ping task to prove the broker/worker wiring end to end."""

from datetime import UTC, datetime

from app.workers.celery_app import celery_app


@celery_app.task(name="system.ping")
def ping() -> dict[str, str]:
    return {"status": "ok", "at": datetime.now(tz=UTC).isoformat()}
