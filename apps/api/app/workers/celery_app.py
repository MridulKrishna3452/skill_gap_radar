"""Celery app for background work: ingestion, extraction, embeddings, parsing, forecasts.

Run with:  celery -A app.workers.celery_app worker --loglevel=INFO
"""

import logging
from typing import Any

from celery import Celery
from celery.signals import after_setup_logger

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
    # Ingestion of many pages (with polite delays) and extraction can take a while.
    task_soft_time_limit=1800,
    task_time_limit=1900,
    result_expires=60 * 60 * 24,
    broker_connection_retry_on_startup=True,
)


@after_setup_logger.connect
def _quiet_http_loggers(*_: Any, **__: Any) -> None:
    # httpx logs request URLs at INFO; Adzuna's API key is a query parameter.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
