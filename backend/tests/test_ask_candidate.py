"""Per-candidate Q&A. Uses the deterministic `fake` Q&A mode so we can
assert exact behavior without an LLM."""

ADMIN = {"email": "admin@example.com", "password": "admin-pass-12345"}


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
