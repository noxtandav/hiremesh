"""Embedder behavior + the embed → upsert flow.

Vector storage on sqlite is JSON, so cosine ranking happens in Python via
the service layer's fallback path. The Postgres path is exercised in M4's
live smoke test.
"""

import math

from app.core.embeddings import fake_embed
from app.models.candidate import Candidate
from app.models.embedding import EMBEDDING_DIM, CandidateEmbedding
from app.services.embeddings import build_document, upsert_embedding

ADMIN = {"email": "admin@example.com", "password": "admin-pass-12345"}


def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def test_fake_embedder_returns_normalized_vector_of_correct_dim():
    v = fake_embed("Backend engineer with Python and Postgres experience")
    assert len(v) == EMBEDDING_DIM
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 1e-6


def test_fake_embedder_clusters_similar_docs():
    a = fake_embed("Senior backend engineer in Pune with Python and Postgres")
    b = fake_embed("Backend engineer Pune Python Postgres FastAPI")
    c = fake_embed("Frontend designer in New York with Figma and Tailwind")

    sim_ab = _cos(a, b)
    sim_ac = _cos(a, c)
    # Documents that share tokens should be more similar than completely
    # disjoint ones. The smart-fake's whole job is to make this true.
    assert sim_ab > sim_ac
    assert sim_ab > 0.2


def test_fake_embedder_is_deterministic():
    a = fake_embed("hello world")
    b = fake_embed("hello world")
    assert a == b


def test_build_document_includes_skills_and_summary(db_session):
    c = Candidate(
        full_name="Asha Rao",
        location="Pune",
        current_title="Backend Engineer",
        skills=["Python", "FastAPI", "Postgres"],
        summary="6 years of fintech backend experience.",
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)

    doc = build_document(db_session, c)
    assert "Asha Rao" in doc
    assert "Pune" in doc
    assert "Python" in doc and "FastAPI" in doc
    assert "fintech" in doc


def test_build_document_includes_full_resume_extracted_text(db_session):
    """Regression: the embedded document used to use only parsed_json['summary'],
    so anything mentioned in the resume body but not lifted into structured
    fields was invisible to semantic search."""
    from app.models.resume import Resume

    c = Candidate(full_name="Asha Rao", skills=["Python"])
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)

    db_session.add(
        Resume(
            candidate_id=c.id,
            filename="r.pdf",
            s3_key="resumes/x.pdf",
            mime="application/pdf",
            is_primary=True,
            parse_status="done",
            parsed_json={"summary": "Backend engineer."},
            extracted_text=(
                "Asha Rao\nBuilt event-driven services using Apache Kafka "
                "and Redis on the payments team."
            ),
        )
    )
    db_session.commit()

    doc = build_document(db_session, c)
    # Full resume body should be present, not just the parsed summary.
    assert "Kafka" in doc
    assert "Redis" in doc


def test_build_document_caps_long_resume_text(db_session):
    from app.services.embeddings import MAX_RESUME_CHARS
    from app.models.resume import Resume

    c = Candidate(full_name="X")
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)

    huge = "lorem ipsum " * 2000  # ~22 k chars, well past the cap
    db_session.add(
        Resume(
            candidate_id=c.id,
            filename="r.pdf",
            s3_key="resumes/x.pdf",
            mime="application/pdf",
            is_primary=True,
            parse_status="done",
            extracted_text=huge,
        )
    )
    db_session.commit()

    doc = build_document(db_session, c)
    # The doc has other parts (name, etc.) so we just check the resume slice
    # didn't blow past the cap by more than a small margin.
    assert len(doc) < MAX_RESUME_CHARS + 500


def test_upsert_embedding_creates_then_updates(db_session):
    c = Candidate(full_name="Asha", skills=["Python"])
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)

    row1 = upsert_embedding(db_session, c.id)
    assert row1 is not None
    first_vector = list(row1.vector)
    assert len(first_vector) == EMBEDDING_DIM

    # Mutating the candidate and re-running upsert updates the row in place.
    c.skills = ["Python", "Postgres", "FastAPI"]
    db_session.commit()
    row2 = upsert_embedding(db_session, c.id)
    assert row2 is not None
    assert row2.id == row1.id  # same row, content/vector replaced
    assert list(row2.vector) != first_vector


def test_upsert_embedding_skips_soft_deleted_candidate(db_session):
    from datetime import UTC, datetime

    c = Candidate(
        full_name="Ghost", skills=["Python"], deleted_at=datetime.now(UTC)
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)

    assert upsert_embedding(db_session, c.id) is None
    assert (
        db_session.query(CandidateEmbedding).filter_by(candidate_id=c.id).count() == 0
    )
