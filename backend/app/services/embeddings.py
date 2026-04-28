"""Build the document we embed for a candidate, and apply the embedding.

One row per candidate (`source='combined'`). Future milestones may split
into per-resume / per-notes rows for finer retrieval.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.embeddings import embed
from app.models.candidate import Candidate
from app.models.embedding import CandidateEmbedding
from app.models.note import Note
from app.models.resume import Resume


def build_document(db: Session, candidate: Candidate) -> str:
    """Compose the text we feed to the embedder.

    Order matters less than coverage — we just want every salient piece of
    information about the candidate to land in the document so token overlap
    drives retrieval.
    """
    parts: list[str] = [candidate.full_name]
    for field in (
        candidate.current_title,
        candidate.current_company,
        candidate.location,
        candidate.summary,
    ):
        if field:
            parts.append(field)
    if candidate.skills:
        parts.append("Skills: " + ", ".join(candidate.skills))
    if candidate.total_exp_years is not None:
        parts.append(f"Experience: {candidate.total_exp_years} years")
    if candidate.notice_period_days is not None:
        parts.append(f"Notice period: {candidate.notice_period_days} days")

    primary = db.scalar(
        select(Resume)
        .where(Resume.candidate_id == candidate.id, Resume.is_primary.is_(True))
        .limit(1)
    )
    if primary is not None and primary.parsed_json:
        # parsed_json["summary"] usually contains the full extracted text.
        summary = primary.parsed_json.get("summary")
        if summary:
            parts.append(str(summary))

    notes = list(
        db.scalars(
            select(Note.body).where(
                Note.candidate_id == candidate.id,
                Note.candidate_job_id.is_(None),  # global notes only for now
            )
        ).all()
    )
    if notes:
        parts.append("Notes: " + " | ".join(notes))

    return "\n".join(parts)


def upsert_embedding(db: Session, candidate_id: int) -> CandidateEmbedding | None:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or candidate.deleted_at is not None:
        return None

    document = build_document(db, candidate)
    if not document.strip():
        return None
    vector = embed(document)

    existing = db.scalar(
        select(CandidateEmbedding).where(
            CandidateEmbedding.candidate_id == candidate_id,
            CandidateEmbedding.source == "combined",
        )
    )
    if existing is None:
        existing = CandidateEmbedding(
            candidate_id=candidate_id,
            source="combined",
            content=document,
            vector=vector,
        )
        db.add(existing)
    else:
        existing.content = document
        existing.vector = vector
    db.commit()
    db.refresh(existing)
    return existing
