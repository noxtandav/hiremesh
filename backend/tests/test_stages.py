"""Stage template: seeding, read by any user, write only by admin."""

ADMIN = {"email": "admin@example.com", "password": "admin-pass-12345"}
DEFAULT_NAMES = [
    "Sourced/Teaser",
    "InMail to be sent",
    "Email cadence initiated",
    "InMail sent",
    "Follow-Up",
    "Not Interested",
    "Interested",
    "Submitted",
]


def _login(client, **creds):
    r = client.post("/auth/login", json=creds)
    assert r.status_code == 200, r.text


def _make_recruiter(client, email="rec@example.com", password="rec-pass-12345"):
    _login(client, **ADMIN)
    client.post(
        "/users",
        json={"email": email, "name": "Rec", "password": password, "role": "recruiter"},
    )
    client.post("/auth/logout")


def test_template_seeded_with_defaults_on_first_boot(client):
    _login(client, **ADMIN)
    r = client.get("/stages/template")
    assert r.status_code == 200
    body = r.json()
    assert [s["name"] for s in body] == DEFAULT_NAMES
    assert [s["position"] for s in body] == list(range(8))


def test_template_seed_is_idempotent(client, db_session):
    from app.services.stages import seed_default_template_if_needed

    inserted = seed_default_template_if_needed(db_session)
    # Already seeded by lifespan; second call inserts nothing.
    assert inserted == 0


def test_recruiter_can_read_template(client):
    _make_recruiter(client)
    _login(client, email="rec@example.com", password="rec-pass-12345")
    r = client.get("/stages/template")
    assert r.status_code == 200
    assert len(r.json()) == 8


def test_recruiter_cannot_edit_template(client):
    _make_recruiter(client)
    _login(client, email="rec@example.com", password="rec-pass-12345")
    r = client.put("/stages/template", json={"stages": [{"name": "Anything"}]})
    assert r.status_code == 403


def test_admin_can_replace_template(client):
    _login(client, **ADMIN)
    r = client.get("/stages/template")
    rows = r.json()

    payload = {
        "stages": [
            {"id": rows[0]["id"], "name": "Sourced"},  # rename in place
            {"name": "Reached out"},  # new
            {"id": rows[7]["id"], "name": "Submitted"},  # keep last
        ]
    }
    r = client.put("/stages/template", json=payload)
    assert r.status_code == 200, r.text
    after = r.json()
    assert [s["name"] for s in after] == ["Sourced", "Reached out", "Submitted"]
    assert [s["position"] for s in after] == [0, 1, 2]

    # Round-trip: GET returns the same shape
    r2 = client.get("/stages/template").json()
    assert [s["name"] for s in r2] == ["Sourced", "Reached out", "Submitted"]
