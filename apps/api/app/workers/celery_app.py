"""Celery app for background work: ingestion, extraction, embeddings, parsing, forecasts.

Run with:  celery -A app.workers.celery_app worker --loglevel=INFO
"""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "skillradar",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],  # never unpickle messages from the broker
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,  # a task killed mid-run is redelivered, so tasks must be idempotent
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=300,
    task_time_limit=360,
    result_expires=60 * 60 * 24,
    broker_connection_retry_on_startup=True,
)
