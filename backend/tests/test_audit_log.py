"""Audit log writes from key actions and the admin viewer endpoint."""

ADMIN = {"email": "admin@example.com", "password": "admin-pass-12345"}
REC = {"email": "rec@example.com", "password": "rec-pass-12345"}


def _login(client, **creds):
    r = client.post("/auth/login", json=creds)
    assert r.status_code == 200, r.text


def _entries(client, **filters):
    return client.get("/admin/audit-log", params=filters).json()


def test_login_records_audit(client):
    _login(client, **ADMIN)
    rows = _entries(client, action="login")
    assert len(rows) >= 1
    assert rows[0]["entity"] == "user"
    assert rows[0]["actor_name"]


def test_user_create_records_audit(client):
    _login(client, **ADMIN)
    client.post(
        "/users",
        json={**REC, "name": "Rec", "role": "recruiter"},
    )
    rows = _entries(client, action="user.create")
    assert len(rows) == 1
    assert rows[0]["payload"]["email"] == REC["email"]


def test_candidate_create_and_soft_delete_recorded(client):
    _login(client, **ADMIN)
    cid = client.post("/candidates", json={"full_name": "Audit Subject"}).json()["id"]
    client.delete(f"/candidates/{cid}")

    create_rows = _entries(client, action="candidate.create")
    delete_rows = _entries(client, action="candidate.soft_delete")
    assert any(r["entity_id"] == cid for r in create_rows)
    assert any(r["entity_id"] == cid for r in delete_rows)


def test_recruiter_cannot_view_audit(client):
    _login(client, **ADMIN)
    client.post(
        "/users",
        json={**REC, "name": "Rec", "role": "recruiter"},
    )
    client.post("/auth/logout")
    _login(client, **REC)
    r = client.get("/admin/audit-log")
    assert r.status_code == 403


def test_filter_by_entity(client):
    _login(client, **ADMIN)
    client.post("/clients", json={"name": "AuditCo"})
    client.post("/candidates", json={"full_name": "Aud Cand"})

    only_clients = _entries(client, entity="client")
    assert all(r["entity"] == "client" for r in only_clients)
    assert any(r["action"] == "client.create" for r in only_clients)


def test_metrics_returns_breakdown(client):
    _login(client, **ADMIN)
    # Add a candidate so the metrics aren't all zero
    client.post("/candidates", json={"full_name": "Metric Subject"})

    r = client.get("/admin/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["candidates"]["active"] >= 1
    assert "open" in body["jobs"]
    assert body["users"]["active"] >= 1
    assert "parse" in body["models"] and "embed" in body["models"]


def test_metrics_admin_only(client):
    _login(client, **ADMIN)
    client.post("/users", json={**REC, "name": "Rec", "role": "recruiter"})
    client.post("/auth/logout")
    _login(client, **REC)
    assert client.get("/admin/metrics").status_code == 403
