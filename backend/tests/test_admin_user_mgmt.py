"""Admin user management: list, patch, deactivate, role change, reset password."""

ADMIN = {"email": "admin@example.com", "password": "admin-pass-12345"}
REC = {"email": "rec@example.com", "password": "rec-pass-12345"}


def _login(client, **creds):
    r = client.post("/auth/login", json=creds)
    assert r.status_code == 200, r.text


def _make_recruiter(client):
    _login(client, **ADMIN)
    client.post(
        "/users",
        json={**REC, "name": "Rec", "role": "recruiter"},
    )
    client.post("/auth/logout")


def test_list_users_admin_only(client):
    _make_recruiter(client)
    _login(client, **REC)
    assert client.get("/users").status_code == 403

    client.post("/auth/logout")
    _login(client, **ADMIN)
    r = client.get("/users")
    assert r.status_code == 200
    emails = {u["email"] for u in r.json()}
    assert ADMIN["email"] in emails
    assert REC["email"] in emails


def test_admin_can_change_recruiter_role(client):
    _make_recruiter(client)
    _login(client, **ADMIN)
    rec = next(u for u in client.get("/users").json() if u["email"] == REC["email"])

    r = client.patch(f"/users/{rec['id']}", json={"role": "admin"})
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_admin_cannot_deactivate_self(client):
    _login(client, **ADMIN)
    me = client.get("/auth/me").json()
    r = client.patch(f"/users/{me['id']}", json={"is_active": False})
    assert r.status_code == 400


def test_cannot_demote_last_admin(client):
    _login(client, **ADMIN)
    me = client.get("/auth/me").json()
    r = client.patch(f"/users/{me['id']}", json={"role": "recruiter"})
    assert r.status_code == 400


def test_admin_can_deactivate_recruiter(client):
    _make_recruiter(client)
    _login(client, **ADMIN)
    rec = next(u for u in client.get("/users").json() if u["email"] == REC["email"])

    r = client.patch(f"/users/{rec['id']}", json={"is_active": False})
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    # Deactivated user cannot log in
    client.post("/auth/logout")
    r2 = client.post("/auth/login", json=REC)
    assert r2.status_code == 401


def test_reset_password_flips_must_change_flag(client):
    _make_recruiter(client)
    _login(client, **ADMIN)
    rec = next(u for u in client.get("/users").json() if u["email"] == REC["email"])

    # Recruiter changes their own password to clear must_change_password
    client.post("/auth/logout")
    _login(client, **REC)
    client.post(
        "/auth/me/password",
        json={"current_password": REC["password"], "new_password": "fresh-pass-9876"},
    )
    me = client.get("/auth/me").json()
    assert me["must_change_password"] is False

    # Admin resets it
    client.post("/auth/logout")
    _login(client, **ADMIN)
    r = client.post(
        f"/users/{rec['id']}/reset-password", json={"new_password": "admin-set-pwd-123"}
    )
    assert r.status_code == 200
    assert r.json()["must_change_password"] is True

    # Old password no longer works; new one does
    client.post("/auth/logout")
    assert (
        client.post("/auth/login", json={**REC, "password": "fresh-pass-9876"}).status_code
        == 401
    )
    assert (
        client.post(
            "/auth/login", json={**REC, "password": "admin-set-pwd-123"}
        ).status_code
        == 200
    )
