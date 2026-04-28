"""Search API: filter-only behavior + semantic ranking on the sqlite fallback.

The Postgres pgvector path is exercised by M4's live smoke test, not here.
"""

ADMIN = {"email": "admin@example.com", "password": "admin-pass-12345"}


def _login(client, **creds):
    r = client.post("/auth/login", json=creds)
    assert r.status_code == 200, r.text


def _make_candidates(client):
    """Three candidates with very different profiles."""
    a = client.post(
        "/candidates",
        json={
            "full_name": "Asha Rao",
            "location": "Pune",
            "current_title": "Backend Engineer",
            "skills": ["Python", "Postgres", "FastAPI", "Kafka"],
            "total_exp_years": 6,
            "summary": "Fintech backend, payments at scale.",
        },
    ).json()
    b = client.post(
        "/candidates",
        json={
            "full_name": "Bo Wang",
            "location": "Bangalore",
            "current_title": "ML Engineer",
            "skills": ["Python", "PyTorch", "MLOps"],
            "total_exp_years": 4,
            "summary": "Recommender systems, NLP.",
        },
    ).json()
    c = client.post(
        "/candidates",
        json={
            "full_name": "Cara Diaz",
            "location": "New York",
            "current_title": "Frontend Designer",
            "skills": ["Figma", "Tailwind", "Accessibility"],
            "total_exp_years": 8,
            "summary": "Design systems for editorial brands.",
        },
    ).json()
    return a, b, c


def test_search_filter_only_by_location(client):
    _login(client, **ADMIN)
    _make_candidates(client)

    r = client.post("/search/candidates", json={"location": "Pune"})
    assert r.status_code == 200
    names = {h["candidate"]["full_name"] for h in r.json()}
    assert names == {"Asha Rao"}


def test_search_filter_only_by_skill(client):
    _login(client, **ADMIN)
    _make_candidates(client)

    r = client.post("/search/candidates", json={"skills": ["pytorch"]})
    names = {h["candidate"]["full_name"] for h in r.json()}
    assert names == {"Bo Wang"}


def test_search_filter_only_by_exp_range(client):
    _login(client, **ADMIN)
    _make_candidates(client)

    r = client.post(
        "/search/candidates", json={"exp_min": 5, "exp_max": 7}
    )
    names = {h["candidate"]["full_name"] for h in r.json()}
    assert names == {"Asha Rao"}


def test_search_filter_excludes_soft_deleted(client):
    _login(client, **ADMIN)
    a, _b, _c = _make_candidates(client)
    client.delete(f"/candidates/{a['id']}")

    r = client.post("/search/candidates", json={"location": "Pune"})
    assert r.json() == []


def test_search_filter_returns_score_null_when_no_q(client):
    _login(client, **ADMIN)
    _make_candidates(client)

    r = client.post("/search/candidates", json={"location": "Pune"})
    body = r.json()
    assert body[0]["score"] is None


def test_search_semantic_ranks_relevant_first(client):
    """Semantic path (sqlite fallback ranks in Python via cosine).

    With a query like 'backend engineer python postgres', Asha (the only
    one with that exact skill profile) should rank higher than the ML
    engineer who shares only 'Python' and far higher than the designer.
    """
    _login(client, **ADMIN)
    _make_candidates(client)

    # Trigger the embed task synchronously by calling the service directly
    # for each candidate (bypasses Celery).
    from app.core.db import SessionLocal
    from app.services.embeddings import upsert_embedding

    with SessionLocal() as s:
        from app.models.candidate import Candidate

        for c in s.scalars(__import__("sqlalchemy").select(Candidate)).all():
            upsert_embedding(s, c.id)

    r = client.post(
        "/search/candidates",
        json={"q": "backend engineer python postgres fintech"},
    )
    hits = r.json()
    assert len(hits) >= 2
    names = [h["candidate"]["full_name"] for h in hits]
    assert names[0] == "Asha Rao"
    # All hits have a score
    assert all(h["score"] is not None for h in hits)


def test_search_semantic_with_filters_intersected(client):
    _login(client, **ADMIN)
    _make_candidates(client)

    from app.core.db import SessionLocal
    from app.services.embeddings import upsert_embedding

    with SessionLocal() as s:
        from app.models.candidate import Candidate

        for c in s.scalars(__import__("sqlalchemy").select(Candidate)).all():
            upsert_embedding(s, c.id)

    r = client.post(
        "/search/candidates",
        json={"q": "engineer with python", "location": "Bangalore"},
    )
    hits = r.json()
    # Only Bo Wang is in Bangalore among the three; filter must shrink result
    # set even though the query embeds-similar to multiple candidates.
    assert {h["candidate"]["full_name"] for h in hits} == {"Bo Wang"}
