"""Candidate CRUD with soft-delete semantics."""

ADMIN = {"email": "admin@example.com", "password": "admin-pass-12345"}


def _login(client, **creds):
    r = client.post("/auth/login", json=creds)
    assert r.status_code == 200, r.text


def test_candidate_crud(client):
    _login(client, **ADMIN)

    r = client.post(
        "/candidates",
        json={
            "full_name": "Asha Rao",
            "email": "asha@example.com",
            "location": "Pune",
            "current_title": "Backend Engineer",
            "skills": ["Python", "Postgres", "FastAPI"],
        },
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]
    assert r.json()["skills"] == ["Python", "Postgres", "FastAPI"]

    r2 = client.patch(f"/candidates/{cid}", json={"location": "Bangalore"})
    assert r2.status_code == 200
    assert r2.json()["location"] == "Bangalore"


def test_soft_delete_excludes_from_default_list(client):
    _login(client, **ADMIN)
    keep = client.post("/candidates", json={"full_name": "Keep Me"}).json()["id"]
    drop = client.post("/candidates", json={"full_name": "Drop Me"}).json()["id"]

    assert client.delete(f"/candidates/{drop}").status_code == 204

    listed_ids = {c["id"] for c in client.get("/candidates").json()}
    assert keep in listed_ids
    assert drop not in listed_ids

    # Hidden but recoverable
    listed_with_deleted = client.get(
        "/candidates", params={"include_deleted": "true"}
    ).json()
    assert any(c["id"] == drop for c in listed_with_deleted)


def test_get_soft_deleted_returns_404(client):
    _login(client, **ADMIN)
    cid = client.post("/candidates", json={"full_name": "Ghost"}).json()["id"]
    client.delete(f"/candidates/{cid}")
    assert client.get(f"/candidates/{cid}").status_code == 404


def test_restore_brings_back(client):
    _login(client, **ADMIN)
    cid = client.post("/candidates", json={"full_name": "Phoenix"}).json()["id"]
    client.delete(f"/candidates/{cid}")
    r = client.post(f"/candidates/{cid}/restore")
    assert r.status_code == 200
    assert r.json()["deleted_at"] is None
    assert client.get(f"/candidates/{cid}").status_code == 200


def test_restore_active_returns_400(client):
    _login(client, **ADMIN)
    cid = client.post("/candidates", json={"full_name": "Already Here"}).json()["id"]
    r = client.post(f"/candidates/{cid}/restore")
    assert r.status_code == 400


def test_cannot_patch_soft_deleted(client):
    _login(client, **ADMIN)
    cid = client.post("/candidates", json={"full_name": "Buried"}).json()["id"]
    client.delete(f"/candidates/{cid}")
    r = client.patch(f"/candidates/{cid}", json={"location": "Mumbai"})
    assert r.status_code == 404
