"""Notes: scoped to a candidate, edit/delete restricted to author or admin."""

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


def _make_candidate(client) -> int:
    return client.post("/candidates", json={"full_name": "Subject"}).json()["id"]


def test_create_and_list_notes(client):
    _login(client, **ADMIN)
    cid = _make_candidate(client)

    r = client.post(f"/candidates/{cid}/notes", json={"body": "Strong python skills"})
    assert r.status_code == 201, r.text
    assert r.json()["body"] == "Strong python skills"

    listed = client.get(f"/candidates/{cid}/notes").json()
    assert len(listed) == 1


def test_notes_on_unknown_candidate_404(client):
    _login(client, **ADMIN)
    assert client.get("/candidates/99999/notes").status_code == 404
    assert (
        client.post("/candidates/99999/notes", json={"body": "x"}).status_code == 404
    )


def test_notes_on_soft_deleted_candidate_404(client):
    _login(client, **ADMIN)
    cid = _make_candidate(client)
    client.delete(f"/candidates/{cid}")
    assert client.get(f"/candidates/{cid}/notes").status_code == 404


def test_recruiter_cannot_edit_other_authors_note(client):
    _make_recruiter(client)

    _login(client, **ADMIN)
    cid = _make_candidate(client)
    nid = client.post(f"/candidates/{cid}/notes", json={"body": "by admin"}).json()[
        "id"
    ]

    client.post("/auth/logout")
    _login(client, **REC)
    r = client.patch(f"/notes/{nid}", json={"body": "hijack"})
    assert r.status_code == 403
    assert client.delete(f"/notes/{nid}").status_code == 403


def test_admin_can_edit_anyones_note(client):
    _make_recruiter(client)

    _login(client, **REC)
    cid = _make_candidate(client)
    nid = client.post(f"/candidates/{cid}/notes", json={"body": "by recruiter"}).json()[
        "id"
    ]
    client.post("/auth/logout")

    _login(client, **ADMIN)
    r = client.patch(f"/notes/{nid}", json={"body": "edited by admin"})
    assert r.status_code == 200
    assert r.json()["body"] == "edited by admin"


def test_author_can_delete_own_note(client):
    _make_recruiter(client)
    _login(client, **REC)
    cid = _make_candidate(client)
    nid = client.post(f"/candidates/{cid}/notes", json={"body": "mine"}).json()["id"]
    assert client.delete(f"/notes/{nid}").status_code == 204
