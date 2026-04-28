"""End-to-end auth flow tests against an in-memory sqlite database."""

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin-pass-12345"


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_bootstrap_creates_admin_on_first_boot(client):
    # The lifespan event runs on TestClient context entry, so the admin should exist.
    r = client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == ADMIN_EMAIL
    assert body["role"] == "admin"
    assert body["must_change_password"] is True


def test_bootstrap_is_idempotent(client, db_session):
    from app.services.users import bootstrap_admin_if_needed

    # Already bootstrapped via lifespan; a second call is a no-op.
    result = bootstrap_admin_if_needed(db_session)
    assert result is None


def test_login_with_wrong_password_returns_401(client):
    r = client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong"})
    assert r.status_code == 401


def test_login_with_unknown_email_returns_401(client):
    r = client.post("/auth/login", json={"email": "nobody@example.com", "password": "x"})
    assert r.status_code == 401


def test_me_requires_cookie(client):
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_me_returns_user_after_login(client):
    client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    r = client.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["email"] == ADMIN_EMAIL


def test_logout_clears_cookie(client):
    client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    r = client.post("/auth/logout")
    assert r.status_code == 204
    # cookie has been cleared, /me should now 401
    r2 = client.get("/auth/me")
    assert r2.status_code == 401


def test_admin_can_create_user(client):
    client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    r = client.post(
        "/users",
        json={
            "email": "rec@example.com",
            "name": "Rec One",
            "password": "rec-pass-12345",
            "role": "recruiter",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "recruiter"
    assert r.json()["must_change_password"] is True


def test_recruiter_cannot_create_user(client):
    # admin creates a recruiter, then we log in as that recruiter and try to create another user
    client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    client.post(
        "/users",
        json={
            "email": "rec@example.com",
            "name": "Rec One",
            "password": "rec-pass-12345",
            "role": "recruiter",
        },
    )
    client.post("/auth/logout")
    r_login = client.post(
        "/auth/login", json={"email": "rec@example.com", "password": "rec-pass-12345"}
    )
    assert r_login.status_code == 200

    r = client.post(
        "/users",
        json={
            "email": "another@example.com",
            "name": "Another",
            "password": "another-pass",
            "role": "recruiter",
        },
    )
    assert r.status_code == 403


def test_create_user_with_existing_email_returns_409(client):
    client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    payload = {
        "email": "dup@example.com",
        "name": "Dup",
        "password": "dup-pass-12345",
        "role": "recruiter",
    }
    assert client.post("/users", json=payload).status_code == 201
    r = client.post("/users", json=payload)
    assert r.status_code == 409


def test_change_password_requires_current_password(client):
    client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    r = client.post(
        "/auth/me/password",
        json={"current_password": "wrong", "new_password": "new-pass-12345"},
    )
    assert r.status_code == 400


def test_change_password_clears_must_change_flag(client):
    client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    r = client.post(
        "/auth/me/password",
        json={"current_password": ADMIN_PASSWORD, "new_password": "new-pass-12345"},
    )
    assert r.status_code == 204
    me = client.get("/auth/me").json()
    assert me["must_change_password"] is False
