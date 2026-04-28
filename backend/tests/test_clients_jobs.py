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
