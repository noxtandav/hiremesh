"""Pool Q&A: classifier + semantic dispatch.

The structured execution path queries `v_candidate_search` which only exists
on Postgres, so it's covered by the M5 live smoke test. Here we test the
classifier and the semantic path (which works on SQLite via the M4 fallback).
"""

from app.services.qa_pool import _fake_classify, _fake_sqlgen
from app.services.qa_pool_query import StructuredQuery

ADMIN = {"email": "admin@example.com", "password": "admin-pass-12345"}


def _login(client, **creds):
    r = client.post("/auth/login", json=creds)
    assert r.status_code == 200, r.text


# ----- classifier --------------------------------------------------------


def test_classifier_picks_structured_for_count_questions():
    assert _fake_classify("How many Python developers in Pune are there?") == "structured"
    assert _fake_classify("count of candidates added last week") == "structured"


def test_classifier_picks_semantic_for_fuzzy_questions():
    assert _fake_classify("backend engineer with fintech experience") == "semantic"


def test_classifier_picks_hybrid_for_filter_plus_fuzzy():
    assert (
        _fake_classify("how many python devs have fintech experience")
        == "hybrid"
    )


# ----- fake SQL gen ------------------------------------------------------


def test_sqlgen_extracts_skill_and_location():
    q = _fake_sqlgen("python devs in Pune")
    cols = {f.column for f in q.filters}
    assert "skills" in cols
    assert "location" in cols


def test_sqlgen_count_for_how_many():
    q = _fake_sqlgen("how many devs are there")
    assert q.aggregate == "count"


def test_sqlgen_extracts_exp_threshold():
    q = _fake_sqlgen("candidates with 5+ years experience")
    exp_filters = [f for f in q.filters if f.column == "total_exp_years"]
    assert len(exp_filters) == 1
    assert exp_filters[0].op == "gte"
    assert exp_filters[0].value == 5.0


# ----- semantic path end-to-end ------------------------------------------


def test_semantic_route_returns_candidates(client):
    _login(client, **ADMIN)

    # Seed three candidates with different profiles.
    a = client.post(
        "/candidates",
        json={
            "full_name": "Asha Rao",
            "location": "Pune",
            "current_title": "Backend Engineer",
            "skills": ["Python", "Postgres", "FastAPI"],
            "summary": "Six years of fintech backend experience.",
        },
    ).json()["id"]
    client.post(
        "/candidates",
        json={
            "full_name": "Bo Wang",
            "location": "Bangalore",
            "current_title": "ML Engineer",
            "skills": ["PyTorch"],
        },
    )
    client.post(
        "/candidates",
        json={
            "full_name": "Cara Diaz",
            "location": "New York",
            "current_title": "Frontend Designer",
            "skills": ["Figma", "Tailwind"],
        },
    )

    # Embed everyone via the service (bypassing Celery).
    from sqlalchemy import select
    from app.core.db import SessionLocal
    from app.models.candidate import Candidate
    from app.services.embeddings import upsert_embedding

    with SessionLocal() as s:
        for c in s.scalars(select(Candidate)).all():
            upsert_embedding(s, c.id)

    # Pure semantic question (no count, no filter) → semantic route.
    r = client.post(
        "/ask/pool",
        json={"question": "backend engineer with fintech experience"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["route"] == "semantic"
    assert body["matched_count"] >= 1
    # Asha (the fintech backend) should be in the citations.
    cited_ids = {c["id"] for c in body["citations"]}
    assert a in cited_ids

    # Every semantic citation carries a numeric score, ordered best-first.
    citations = body["citations"]
    assert all(isinstance(c["score"], (int, float)) for c in citations)
    scores = [c["score"] for c in citations]
    assert scores == sorted(scores, reverse=True)
    assert body["matched_count"] == len(citations)

    # Percentile is a true rank within the pool of 3 candidates with embeddings:
    # rank 1 → 100, rank 2 → 66.7, rank 3 → 33.3.
    percentiles = [c["percentile"] for c in citations]
    assert all(0 < p <= 100 for p in percentiles)
    assert percentiles == sorted(percentiles, reverse=True)
    assert percentiles[0] == 100.0
    if len(percentiles) == 3:
        assert percentiles[1] == 66.7
        assert percentiles[2] == 33.3


def test_pool_q_with_no_results(client):
    _login(client, **ADMIN)
    r = client.post(
        "/ask/pool", json={"question": "blockchain expert with quantum cryptography"}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["route"] in {"structured", "semantic", "hybrid"}
    assert "answer" in body
