from app.workers import tasks  # noqa: F401  (registers tasks)
from app.workers.celery_app import celery_app


def test_phase1_tasks_are_registered() -> None:
    expected = {
        "system.ping",
        "ingestion.run",
        "extraction.extract_pending",
        "extraction.reextract_stale",
        "analytics.refresh_demand",
        "curriculum.parse_document",
    }
    assert expected <= set(celery_app.tasks)
