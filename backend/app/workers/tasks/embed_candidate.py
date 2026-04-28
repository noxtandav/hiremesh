"""Async task: compute and store a candidate's embedding."""

import logging

from app.core import db as db_module
from app.services.embeddings import upsert_embedding
from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="embed_candidate", bind=True, max_retries=2)
def embed_candidate(self, candidate_id: int) -> dict:
    with db_module.SessionLocal() as db:
        try:
            row = upsert_embedding(db, candidate_id)
            if row is None:
                return {"status": "skipped", "candidate_id": candidate_id}
            return {"status": "ok", "candidate_id": candidate_id}
        except Exception as exc:  # noqa: BLE001
            log.exception("embed_candidate %s failed", candidate_id)
            raise self.retry(exc=exc, countdown=15) from exc
