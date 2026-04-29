"""Per-candidate Q&A. Uses the deterministic `fake` Q&A mode so we can
assert exact behavior without an LLM."""

from __future__ import annotations

import io

import pytest

from app.api import resumes as resumes_api
from app.core import storage
from app.workers.tasks import parse_resume as parse_task

ADMIN = {"email": "admin@example.com", "password": "admin-pass-12345"}


@pytest.fixture
def fake_storage(monkeypatch):
    blobs: dict[str, bytes] = {}

    def put_object(key: str, body, content_type: str) -> None:
        if hasattr(body, "read"):
            body = body.read()
        blobs[key] = body

    def get_object(key: str) -> bytes:
        return blobs[key]

    def presigned_get_url(key: str, expires_in: int = 300) -> str:
        return f"http://stub.test/{key}?ttl={expires_in}"

    def delete_object(key: str) -> None:
        blobs.pop(key, None)

    for mod in (storage, resumes_api.storage, parse_task.storage):
        monkeypatch.setattr(mod, "put_object", put_object, raising=True)
        monkeypatch.setattr(mod, "get_object", get_object, raising=True)
        monkeypatch.setattr(mod, "presigned_get_url", presigned_get_url, raising=True)
        monkeypatch.setattr(mod, "delete_object", delete_object, raising=True)
    return blobs


@pytest.fixture
def inline_parse(monkeypatch):
    def _enqueue(resume_id: int) -> None:
        parse_task.parse_resume.run(resume_id)

    monkeypatch.setattr(resumes_api, "_enqueue_parse", _enqueue, raising=True)
    from app.workers.tasks import embed_candidate as embed_task

    monkeypatch.setattr(
        embed_task.embed_candidate,
        "delay",
        lambda candidate_id: embed_task.embed_candidate.run(candidate_id),
        raising=True,
    )


def _login(client, **creds):
    r = client.post("/auth/login", json=creds)
    assert r.status_code == 200, r.text


def _make_candidate(client) -> int:
    r = client.post(
        "/candidates",
        json={
            "full_name": "Asha Rao",
            "location": "Pune",
            "current_title": "Backend Engineer",
            "skills": ["Python", "Postgres", "FastAPI"],
            "summary": "Six years of fintech backend experience at Razorpay.",
        },
    )
    return r.json()["id"]


def test_ask_returns_answer_with_citations(client):
    _login(client, **ADMIN)
    cid = _make_candidate(client)
    client.post(f"/candidates/{cid}/notes", json={"body": "Notice period: 30 days."})

    r = client.post(
        f"/ask/candidate/{cid}", json={"question": "What is her notice period?"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "answer" in body
    assert "30 days" in body["answer"].lower() or "notice" in body["answer"].lower()
    # Profile + at least one note citation
    types = {c["type"] for c in body["citations"]}
    assert "profile" in types
    assert "note" in types


def test_ask_handles_no_match_gracefully(client):
    _login(client, **ADMIN)
    cid = _make_candidate(client)
    r = client.post(
        f"/ask/candidate/{cid}",
        json={"question": "What is the candidate's favorite spaghetti recipe?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "couldn't find" in body["answer"].lower() or "not" in body["answer"].lower()


def test_ask_unknown_candidate_404(client):
    _login(client, **ADMIN)
    r = client.post("/ask/candidate/99999", json={"question": "anything"})
    assert r.status_code == 404


def test_ask_soft_deleted_candidate_404(client):
    _login(client, **ADMIN)
    cid = _make_candidate(client)
    client.delete(f"/candidates/{cid}")
    r = client.post(f"/ask/candidate/{cid}", json={"question": "anything"})
    assert r.status_code == 404


def test_ask_finds_term_only_in_resume_body(
    client, fake_storage, inline_parse
):
    """Regression: previously the resume context only included parsed_json's
    'summary' field, so any tech mentioned in prose (project descriptions,
    work history) but not lifted into structured skills was invisible to Q&A.
    """
    _login(client, **ADMIN)
    cid = client.post(
        "/candidates", json={"full_name": "Asha Rao"}
    ).json()["id"]

    # Resume body mentions Apache Kafka in prose. The fake parser only picks
    # up explicit "Skills:" lines, so without storing the full extracted
    # text, Kafka would never reach the Q&A context.
    payload = (
        b"Asha Rao\nasha@example.com\n"
        b"Senior Backend Engineer with deep payments experience.\n"
        b"Built event-driven microservices using Apache Kafka and Redis.\n"
        b"Skills: Python, FastAPI, Postgres\n"
    )
    client.post(
        f"/candidates/{cid}/resumes",
        files={"file": ("a.pdf", io.BytesIO(payload), "application/pdf")},
    )

    r = client.post(
        f"/ask/candidate/{cid}", json={"question": "Does she know Kafka?"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "kafka" in body["answer"].lower()
    types = {c["type"] for c in body["citations"]}
    assert "resume" in types


def test_ask_includes_resume_citation_when_resume_present(
    client, db_session
):
    _login(client, **ADMIN)
    cid = _make_candidate(client)
    # Insert a resume row with parsed_json directly (skip the upload pipeline).
    from app.models.resume import Resume

    db_session.add(
        Resume(
            candidate_id=cid,
            filename="r.pdf",
            s3_key="resumes/x.pdf",
            mime="application/pdf",
            is_primary=True,
            parse_status="done",
            parsed_json={"summary": "Worked at Razorpay on payment systems."},
        )
    )
    db_session.commit()

    r = client.post(
        f"/ask/candidate/{cid}", json={"question": "Where did she work?"}
    )
    assert r.status_code == 200
    types = {c["type"] for c in r.json()["citations"]}
    assert "resume" in types
