"""Clients + Jobs CRUD, including the per-job stage-copy invariant."""

ADMIN = {"email": "admin@example.com", "password": "admin-pass-12345"}


def _login(client, **creds):
    r = client.post("/auth/login", json=creds)
    assert r.status_code == 200, r.text


def test_client_crud(client):
    _login(client, **ADMIN)

    r = client.post("/clients", json={"name": "Acme Corp", "notes": "intro from X"})
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    assert client.get(f"/clients/{cid}").json()["name"] == "Acme Corp"

    r2 = client.patch(f"/clients/{cid}", json={"notes": "updated"})
    assert r2.status_code == 200
    assert r2.json()["notes"] == "updated"

    listed = client.get("/clients").json()
    assert any(c["id"] == cid for c in listed)

    r3 = client.delete(f"/clients/{cid}")
    assert r3.status_code == 204
    assert client.get(f"/clients/{cid}").status_code == 404


def test_create_job_copies_stage_template(client):
    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "JobCo"}).json()["id"]

    r = client.post(
        "/jobs",
        json={
            "client_id": cid,
            "title": "Senior Backend Engineer",
            "location": "Pune",
            "exp_min": 5,
            "exp_max": 9,
            "ctc_min": 2000000,
            "ctc_max": 3500000,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["client_id"] == cid
    assert body["status"] == "open"
    assert len(body["stages"]) == 8
    assert [s["name"] for s in body["stages"]][0] == "Sourced/Teaser"
    assert [s["position"] for s in body["stages"]] == list(range(8))


def test_job_stages_are_independent_per_job(client):
    """Editing the template after a job is created must NOT affect that job's stages."""
    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "C"}).json()["id"]
    job1 = client.post("/jobs", json={"client_id": cid, "title": "Job 1"}).json()
    template = client.get("/stages/template").json()

    # Reduce the template to a single stage
    client.put(
        "/stages/template",
        json={"stages": [{"id": template[0]["id"], "name": "Sourced"}]},
    )

    # Existing job's stages must still be the original 8
    job1_after = client.get(f"/jobs/{job1['id']}").json()
    assert len(job1_after["stages"]) == 8

    # A new job copies the new (1-stage) template
    job2 = client.post("/jobs", json={"client_id": cid, "title": "Job 2"}).json()
    assert len(job2["stages"]) == 1
    assert job2["stages"][0]["name"] == "Sourced"


def test_cannot_delete_client_with_jobs(client):
    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "BlockedCo"}).json()["id"]
    client.post("/jobs", json={"client_id": cid, "title": "Some Role"})

    r = client.delete(f"/clients/{cid}")
    assert r.status_code == 409


def test_create_job_under_unknown_client_returns_404(client):
    _login(client, **ADMIN)
    r = client.post("/jobs", json={"client_id": 99999, "title": "Lost"})
    assert r.status_code == 404


def test_job_range_validation(client):
    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "RangeCo"}).json()["id"]
    r = client.post(
        "/jobs",
        json={"client_id": cid, "title": "Bad", "exp_min": 9, "exp_max": 5},
    )
    assert r.status_code == 422


def test_job_status_transition(client):
    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "StatusCo"}).json()["id"]
    job = client.post("/jobs", json={"client_id": cid, "title": "Lead"}).json()
    r = client.patch(f"/jobs/{job['id']}", json={"status": "on-hold"})
    assert r.status_code == 200
    assert r.json()["status"] == "on-hold"


def test_jobs_list_filterable_by_client_and_status(client):
    _login(client, **ADMIN)
    a = client.post("/clients", json={"name": "A"}).json()["id"]
    b = client.post("/clients", json={"name": "B"}).json()["id"]
    j_a = client.post("/jobs", json={"client_id": a, "title": "A1"}).json()
    client.post("/jobs", json={"client_id": b, "title": "B1"})
    client.patch(f"/jobs/{j_a['id']}", json={"status": "closed"})

    only_a = client.get("/jobs", params={"client_id": a}).json()
    assert {j["id"] for j in only_a} == {j_a["id"]}

    closed = client.get("/jobs", params={"status_filter": "closed"}).json()
    assert any(j["id"] == j_a["id"] for j in closed)


def test_clients_list_returns_zero_stats_for_brand_new_client(client):
    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "Fresh"}).json()["id"]

    rows = client.get("/clients").json()
    row = next(c for c in rows if c["id"] == cid)
    assert row["jobs_open"] == 0
    assert row["jobs_total"] == 0
    assert row["candidates_total"] == 0
    assert row["candidates_recent"] == 0


def test_clients_list_counts_jobs_open_vs_total(client):
    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "Acme"}).json()["id"]
    client.post("/jobs", json={"client_id": cid, "title": "Open A"})
    client.post("/jobs", json={"client_id": cid, "title": "Open B"})
    closed = client.post(
        "/jobs", json={"client_id": cid, "title": "Done"}
    ).json()
    client.patch(f"/jobs/{closed['id']}", json={"status": "closed"})

    row = next(c for c in client.get("/clients").json() if c["id"] == cid)
    assert row["jobs_total"] == 3
    assert row["jobs_open"] == 2  # closed one excluded


def test_clients_list_counts_distinct_candidates(client):
    """Same candidate linked to two jobs of the same client counts once."""
    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "Pivot"}).json()["id"]
    j1 = client.post("/jobs", json={"client_id": cid, "title": "Backend"}).json()
    j2 = client.post("/jobs", json={"client_id": cid, "title": "Platform"}).json()

    a = client.post("/candidates", json={"full_name": "Asha"}).json()["id"]
    b = client.post("/candidates", json={"full_name": "Ben"}).json()["id"]

    client.post(f"/jobs/{j1['id']}/candidates", json={"candidate_id": a})
    client.post(f"/jobs/{j2['id']}/candidates", json={"candidate_id": a})
    client.post(f"/jobs/{j1['id']}/candidates", json={"candidate_id": b})

    row = next(c for c in client.get("/clients").json() if c["id"] == cid)
    assert row["candidates_total"] == 2  # Asha and Ben, deduped


def test_clients_list_excludes_soft_deleted_candidates(client):
    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "Vanish"}).json()["id"]
    j = client.post("/jobs", json={"client_id": cid, "title": "T"}).json()
    a = client.post("/candidates", json={"full_name": "Active"}).json()["id"]
    g = client.post("/candidates", json={"full_name": "Ghost"}).json()["id"]
    client.post(f"/jobs/{j['id']}/candidates", json={"candidate_id": a})
    client.post(f"/jobs/{j['id']}/candidates", json={"candidate_id": g})
    client.delete(f"/candidates/{g}")  # soft-delete

    row = next(c for c in client.get("/clients").json() if c["id"] == cid)
    assert row["candidates_total"] == 1  # ghost excluded


def test_clients_list_recent_window(client, db_session):
    """Candidates linked >7d ago don't count toward `candidates_recent`,
    but they still count toward `candidates_total`."""
    from datetime import UTC, datetime, timedelta

    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "Window"}).json()["id"]
    j = client.post("/jobs", json={"client_id": cid, "title": "T"}).json()
    cand = client.post("/candidates", json={"full_name": "Old"}).json()["id"]
    client.post(f"/jobs/{j['id']}/candidates", json={"candidate_id": cand})

    # Backdate the link so it falls outside the 7-day window.
    from app.models.pipeline import CandidateJob

    link = db_session.query(CandidateJob).filter_by(candidate_id=cand).first()
    assert link is not None
    link.linked_at = datetime.now(UTC) - timedelta(days=30)
    db_session.commit()

    row = next(c for c in client.get("/clients").json() if c["id"] == cid)
    assert row["candidates_total"] == 1
    assert row["candidates_recent"] == 0


def test_jobs_list_returns_zero_stats_for_brand_new_job(client):
    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "Acme"}).json()["id"]
    j = client.post("/jobs", json={"client_id": cid, "title": "Empty"}).json()

    rows = client.get("/jobs", params={"client_id": cid}).json()
    row = next(x for x in rows if x["id"] == j["id"])
    assert row["candidates_total"] == 0
    assert row["candidates_recent"] == 0
    assert row["moves_recent"] == 0


def test_jobs_list_counts_distinct_candidates(client):
    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "X"}).json()["id"]
    j = client.post("/jobs", json={"client_id": cid, "title": "T"}).json()

    a = client.post("/candidates", json={"full_name": "A"}).json()["id"]
    b = client.post("/candidates", json={"full_name": "B"}).json()["id"]
    client.post(f"/jobs/{j['id']}/candidates", json={"candidate_id": a})
    client.post(f"/jobs/{j['id']}/candidates", json={"candidate_id": b})

    row = next(
        x for x in client.get("/jobs", params={"client_id": cid}).json()
        if x["id"] == j["id"]
    )
    assert row["candidates_total"] == 2


def test_jobs_list_excludes_soft_deleted_candidates(client):
    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "X"}).json()["id"]
    j = client.post("/jobs", json={"client_id": cid, "title": "T"}).json()

    a = client.post("/candidates", json={"full_name": "A"}).json()["id"]
    g = client.post("/candidates", json={"full_name": "Ghost"}).json()["id"]
    client.post(f"/jobs/{j['id']}/candidates", json={"candidate_id": a})
    client.post(f"/jobs/{j['id']}/candidates", json={"candidate_id": g})
    client.delete(f"/candidates/{g}")

    row = next(
        x for x in client.get("/jobs", params={"client_id": cid}).json()
        if x["id"] == j["id"]
    )
    assert row["candidates_total"] == 1
    assert row["candidates_recent"] == 1


def test_jobs_list_recent_window(client, db_session):
    """Backdated link → not in candidates_recent, but still in candidates_total."""
    from datetime import UTC, datetime, timedelta

    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "X"}).json()["id"]
    j = client.post("/jobs", json={"client_id": cid, "title": "T"}).json()
    cand = client.post("/candidates", json={"full_name": "Old"}).json()["id"]
    client.post(f"/jobs/{j['id']}/candidates", json={"candidate_id": cand})

    from app.models.pipeline import CandidateJob

    link = db_session.query(CandidateJob).filter_by(candidate_id=cand).first()
    assert link is not None
    link.linked_at = datetime.now(UTC) - timedelta(days=30)
    db_session.commit()

    row = next(
        x for x in client.get("/jobs", params={"client_id": cid}).json()
        if x["id"] == j["id"]
    )
    assert row["candidates_total"] == 1
    assert row["candidates_recent"] == 0


def test_jobs_list_moves_recent_counts_transitions(client):
    """Linking creates an initial transition row; moving creates another.
    Both fall within the 7-day window for a freshly-created link."""
    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "X"}).json()["id"]
    j = client.post(
        "/jobs", json={"client_id": cid, "title": "T"}
    ).json()
    a = client.post("/candidates", json={"full_name": "A"}).json()["id"]
    link = client.post(
        f"/jobs/{j['id']}/candidates", json={"candidate_id": a}
    ).json()
    # Move to a different stage in the job's stage list.
    other_stage = next(
        s for s in j["stages"] if s["id"] != link["current_stage_id"]
    )
    client.patch(
        f"/candidate-jobs/{link['id']}", json={"stage_id": other_stage["id"]}
    )

    row = next(
        x for x in client.get("/jobs", params={"client_id": cid}).json()
        if x["id"] == j["id"]
    )
    # 1 initial-link transition + 1 move = 2
    assert row["moves_recent"] == 2

