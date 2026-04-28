"""Async task: pull resume from object storage, run the parser, apply fields.

Status transitions: pending → parsing → done | failed.

Always runs through the same `apply_parsed_fields` path that the API uses, so
the sticky-edit invariant cannot be circumvented.
"""

import logging
import traceback

from app.core import db as db_module
from app.core import llm, storage
from app.models.resume import Resume
from app.services.candidates import apply_parsed_fields
from app.services.parsing import extract_text
from app.workers.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(name="parse_resume", bind=True, max_retries=2)
def parse_resume(self, resume_id: int) -> dict:
    with db_module.SessionLocal() as db:
        resume = db.get(Resume, resume_id)
        if resume is None:
            log.warning("parse_resume: resume %s not found", resume_id)
            return {"status": "missing"}

        resume.parse_status = "parsing"
        resume.parse_error = None
        db.commit()

        try:
            body = storage.get_object(resume.s3_key)
            text = extract_text(resume.filename, body)
            parsed = llm.parse_resume_text(text)

            resume.parsed_json = parsed

            from app.models.candidate import Candidate

            candidate = db.get(Candidate, resume.candidate_id)
            applied: list[str] = []
            if candidate is not None:
                applied = apply_parsed_fields(db, candidate, parsed)

            resume.parse_status = "done"
            db.commit()

            # Auto-refresh the candidate's embedding now that fields/skills
            # have been updated. Local import keeps celery_app from circular-
            # importing during startup.
            from app.workers.tasks.embed_candidate import embed_candidate

            embed_candidate.delay(resume.candidate_id)

            return {"status": "done", "applied": applied}
        except Exception as exc:  # noqa: BLE001
            log.exception("parse_resume %s failed", resume_id)
            resume.parse_status = "failed"
            resume.parse_error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[:1500]}"
            db.commit()
            raise self.retry(exc=exc, countdown=15) from exc
