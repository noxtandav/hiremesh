"""POST /admin/reparse/resumes — bulk reparse endpoint.

Two-phase contract: a no-confirm call returns the count for the UI to show
in a confirmation dialog; the confirmed call resets statuses and enqueues
parse tasks for every resume in the database.
"""

from __future__ import annotations

import pytest

from app.workers.tasks import parse_resume as parse_task

ADMIN = {"email": "admin@example.com", "password": "admin-pass-12345"}


def _login(client, **creds):
    r = client.post("/auth/login", json=creds)
    assert r.status_code == 200, r.text


@pytest.fixture
def captured_parse(monkeypatch):
    """Replace parse_resume.delay so the endpoint can be exercised without
    pulling in Celery / Redis / the LLM."""
    captured: list[int] = []
    monkeypatch.setattr(
        parse_task.parse_resume,
        "delay",
        lambda rid: captured.append(rid),
        raising=True,
    )
    return captured


def _seed_resumes(client, db_session, count: int = 3, status: str = "done"):
    """Insert N resumes against fresh candidates, returning their ids."""
    from app.models.candidate import Candidate
    from app.models.resume import Resume

    rids: list[int] = []
    for i in range(count):
        c = Candidate(full_name=f"User {i}")
        db_session.add(c)
        db_session.flush()
        r = Resume(
            candidate_id=c.id,
            filename=f"r{i}.pdf",
            s3_key=f"resumes/{c.id}/x.pdf",
            mime="application/pdf",
            is_primary=True,
            parse_status=status,
            parse_error="prior error" if status == "failed" else None,
        )
        db_session.add(r)
        db_session.flush()
        rids.append(r.id)
    db_session.commit()
    return rids


def test_reparse_dry_run_returns_count(client, db_session, captured_parse):
    _login(client, **ADMIN)
    _seed_resumes(client, db_session, count=4)

    r = client.post("/admin/reparse/resumes")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["would_enqueue"] == 4
    assert "reparse" in body["warning"].lower()

    # No tasks queued, no statuses changed.
    assert captured_parse == []
    from app.models.resume import Resume

    statuses = {r.parse_status for r in db_session.query(Resume).all()}
    assert statuses == {"done"}


def test_reparse_confirmed_enqueues_all(client, db_session, captured_parse):
    _login(client, **ADMIN)
    rids = _seed_resumes(client, db_session, count=3, status="done")

    r = client.post("/admin/reparse/resumes?confirm=true")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reparsed"] is True
    assert body["enqueued"] == 3

    # Every resume id was passed to .delay
    assert sorted(captured_parse) == sorted(rids)


def test_reparse_resets_status_and_clears_error(
    client, db_session, captured_parse
):
    _login(client, **ADMIN)
    _seed_resumes(client, db_session, count=2, status="failed")

    client.post("/admin/reparse/resumes?confirm=true")

    from app.models.resume import Resume

    db_session.expire_all()  # drop any cached session state
    rows = db_session.query(Resume).all()
    assert all(r.parse_status == "pending" for r in rows)
    assert all(r.parse_error is None for r in rows)


def test_reparse_with_no_resumes(client, captured_parse):
    _login(client, **ADMIN)
    r = client.post("/admin/reparse/resumes")
    assert r.status_code == 200
    assert r.json()["would_enqueue"] == 0

    r2 = client.post("/admin/reparse/resumes?confirm=true")
    assert r2.status_code == 200
    assert r2.json()["enqueued"] == 0
    assert captured_parse == []


def test_reparse_audit_log_entry(client, db_session, captured_parse):
    _login(client, **ADMIN)
    _seed_resumes(client, db_session, count=2)

    client.post("/admin/reparse/resumes?confirm=true")

    rows = client.get(
        "/admin/audit-log", params={"action": "resumes.reparse_all"}
    ).json()
    assert len(rows) >= 1
    assert rows[0]["entity"] == "system"
    assert rows[0]["payload"]["enqueued"] == 2


def test_reparse_requires_admin(client, db_session, captured_parse):
    _login(client, **ADMIN)
    # Create a recruiter and switch to them.
    client.post(
        "/users",
        json={
            "email": "rec@example.com",
            "name": "Rec",
            "password": "rec-pass-12345",
            "role": "recruiter",
        },
    )
    client.post("/auth/logout")
    client.post("/auth/login", json={"email": "rec@example.com", "password": "rec-pass-12345"})

    r = client.post("/admin/reparse/resumes")
    assert r.status_code == 403


def test_reparse_unauthenticated(client):
    r = client.post("/admin/reparse/resumes")
    assert r.status_code == 401
