"""End-to-end tests for the client role.

The client role scopes a user to a single client_id. Visibility rules are
enforced per-endpoint via app/core/visibility.py — these tests verify each
boundary holds.

Setup pattern: admin creates two clients (Acme and Globex), seeds jobs and
candidates for both, creates a client-role user tagged to Acme. Then we log
in as the client-role user and check what they can/can't see and do.
"""

from __future__ import annotations

import io

import pytest

from app.api import resumes as resumes_api
from app.core import storage
from app.workers.tasks import parse_resume as parse_task

ADMIN = {"email": "admin@example.com", "password": "admin-pass-12345"}


def _login(client, **creds):
    r = client.post("/auth/login", json=creds)
    assert r.status_code == 200, r.text


@pytest.fixture
def fake_storage(monkeypatch):
    blobs: dict[str, bytes] = {}

    def put_object(key: str, body, content_type: str) -> None:
        if hasattr(body, "read"):
            body = body.read()
        blobs[key] = body

    def get_object(key: str) -> bytes:
        return blobs[key]

    def presigned_get_url(key: str, expires_in: int = 300) -> str:
        return f"http://stub.test/{key}?ttl={expires_in}"

    def delete_object(key: str) -> None:
        blobs.pop(key, None)

    for mod in (storage, resumes_api.storage, parse_task.storage):
        monkeypatch.setattr(mod, "put_object", put_object, raising=True)
        monkeypatch.setattr(mod, "get_object", get_object, raising=True)
        monkeypatch.setattr(mod, "presigned_get_url", presigned_get_url, raising=True)
        monkeypatch.setattr(mod, "delete_object", delete_object, raising=True)
    return blobs


@pytest.fixture
def captured_enqueue(monkeypatch):
    captured: list[int] = []
    monkeypatch.setattr(
        resumes_api, "_enqueue_parse", lambda rid: captured.append(rid), raising=True
    )
    return captured


@pytest.fixture
def two_clients_setup(client):
    """Acme + Globex, with jobs and candidates linked into each."""
    _login(client, **ADMIN)

    acme = client.post("/clients", json={"name": "Acme"}).json()["id"]
    globex = client.post("/clients", json={"name": "Globex"}).json()["id"]

    acme_job = client.post(
        "/jobs", json={"client_id": acme, "title": "Acme Backend"}
    ).json()
    globex_job = client.post(
        "/jobs", json={"client_id": globex, "title": "Globex Frontend"}
    ).json()

    asha = client.post("/candidates", json={"full_name": "Asha"}).json()["id"]
    ben = client.post("/candidates", json={"full_name": "Ben"}).json()["id"]
    cara = client.post("/candidates", json={"full_name": "Cara"}).json()["id"]

    # Asha and Ben → Acme. Cara → Globex.
    client.post(f"/jobs/{acme_job['id']}/candidates", json={"candidate_id": asha})
    client.post(f"/jobs/{acme_job['id']}/candidates", json={"candidate_id": ben})
    client.post(f"/jobs/{globex_job['id']}/candidates", json={"candidate_id": cara})

    # Create the client-role user, tagged to Acme.
    client.post(
        "/users",
        json={
            "email": "acme-hr@example.com",
            "name": "Acme HR",
            "password": "acme-pass-12345",
            "role": "client",
            "client_id": acme,
        },
    )
    client.post("/auth/logout")

    return {
        "acme": acme,
        "globex": globex,
        "acme_job": acme_job,
        "globex_job": globex_job,
        "asha": asha,
        "ben": ben,
        "cara": cara,
    }


def _login_as_acme_client(client):
    client.post(
        "/auth/login",
        json={"email": "acme-hr@example.com", "password": "acme-pass-12345"},
    )


# ----- user creation validation -----------------------------------------


def test_create_client_role_requires_client_id(client):
    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "Acme"}).json()["id"]
    r = client.post(
        "/users",
        json={
            "email": "x@example.com",
            "name": "X",
            "password": "long-pass-123",
            "role": "client",
        },
    )
    assert r.status_code == 400
    assert "client_id" in r.json()["detail"]

    # Now with client_id — works.
    r2 = client.post(
        "/users",
        json={
            "email": "x@example.com",
            "name": "X",
            "password": "long-pass-123",
            "role": "client",
            "client_id": cid,
        },
    )
    assert r2.status_code == 201
    assert r2.json()["client_id"] == cid
    assert r2.json()["role"] == "client"


def test_create_admin_with_client_id_rejected(client):
    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "Acme"}).json()["id"]
    r = client.post(
        "/users",
        json={
            "email": "x@example.com",
            "name": "X",
            "password": "long-pass-123",
            "role": "admin",
            "client_id": cid,
        },
    )
    assert r.status_code == 400


def test_user_list_hydrates_client_name(client):
    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "Acme"}).json()["id"]
    client.post(
        "/users",
        json={
            "email": "tagged@example.com",
            "name": "Tagged",
            "password": "long-pass-123",
            "role": "client",
            "client_id": cid,
        },
    )

    rows = client.get("/users").json()
    tagged = next(u for u in rows if u["email"] == "tagged@example.com")
    assert tagged["client_id"] == cid
    assert tagged["client_name"] == "Acme"

    # Admin user has no tag — both should be null.
    me = next(u for u in rows if u["email"] == "admin@example.com")
    assert me["client_id"] is None
    assert me["client_name"] is None


def test_create_user_response_includes_client_name(client):
    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "Globex"}).json()["id"]
    r = client.post(
        "/users",
        json={
            "email": "new@example.com",
            "name": "New",
            "password": "long-pass-123",
            "role": "client",
            "client_id": cid,
        },
    )
    assert r.json()["client_name"] == "Globex"


def test_create_client_role_with_unknown_client_404(client):
    _login(client, **ADMIN)
    r = client.post(
        "/users",
        json={
            "email": "x@example.com",
            "name": "X",
            "password": "long-pass-123",
            "role": "client",
            "client_id": 99999,
        },
    )
    assert r.status_code == 404


# ----- visibility: clients -------------------------------------------------


def test_client_sees_only_own_client(client, two_clients_setup):
    s = two_clients_setup
    _login_as_acme_client(client)

    rows = client.get("/clients").json()
    assert {c["id"] for c in rows} == {s["acme"]}

    # Direct fetch of own client works
    assert client.get(f"/clients/{s['acme']}").status_code == 200
    # Other client is hidden as 404
    assert client.get(f"/clients/{s['globex']}").status_code == 404


def test_client_cannot_create_or_delete_clients(client, two_clients_setup):
    _login_as_acme_client(client)
    r = client.post("/clients", json={"name": "Forbidden Co"})
    assert r.status_code == 403
    r2 = client.delete(f"/clients/{two_clients_setup['acme']}")
    assert r2.status_code == 403


# ----- visibility: jobs ---------------------------------------------------


def test_client_sees_only_own_jobs(client, two_clients_setup):
    s = two_clients_setup
    _login_as_acme_client(client)

    jobs = client.get("/jobs").json()
    assert {j["id"] for j in jobs} == {s["acme_job"]["id"]}

    # Filter by other client returns empty
    other = client.get("/jobs", params={"client_id": s["globex"]}).json()
    assert other == []

    # Direct detail on other client's job is 404
    assert client.get(f"/jobs/{s['globex_job']['id']}").status_code == 404


def test_client_cannot_create_or_delete_jobs(client, two_clients_setup):
    s = two_clients_setup
    _login_as_acme_client(client)
    r = client.post(
        "/jobs", json={"client_id": s["acme"], "title": "From client"}
    )
    assert r.status_code == 403
    r2 = client.delete(f"/jobs/{s['acme_job']['id']}")
    assert r2.status_code == 403


# ----- visibility: candidates ---------------------------------------------


def test_client_sees_only_linked_candidates(client, two_clients_setup):
    s = two_clients_setup
    _login_as_acme_client(client)

    rows = client.get("/candidates").json()
    assert {c["id"] for c in rows} == {s["asha"], s["ben"]}

    assert client.get(f"/candidates/{s['cara']}").status_code == 404


def test_client_cannot_soft_delete_candidate(client, two_clients_setup):
    s = two_clients_setup
    _login_as_acme_client(client)
    r = client.delete(f"/candidates/{s['asha']}")
    assert r.status_code == 403


def test_client_cannot_create_candidate_directly(client, two_clients_setup):
    """POST /candidates without going through bulk-import is admin/recruiter
    only — clients have no concept of unlinked talent base."""
    _login_as_acme_client(client)
    r = client.post("/candidates", json={"full_name": "Direct"})
    assert r.status_code == 403


def test_client_can_edit_visible_candidate(client, two_clients_setup):
    s = two_clients_setup
    _login_as_acme_client(client)
    r = client.patch(f"/candidates/{s['asha']}", json={"location": "Pune"})
    assert r.status_code == 200
    assert r.json()["location"] == "Pune"


def test_client_cannot_edit_invisible_candidate(client, two_clients_setup):
    s = two_clients_setup
    _login_as_acme_client(client)
    r = client.patch(f"/candidates/{s['cara']}", json={"location": "Pune"})
    assert r.status_code == 404


def test_client_duplicates_filtered_to_own_pool(client, two_clients_setup):
    """If a candidate exists in another client's pool with a matching email,
    the client-role user must not see them via the duplicates endpoint —
    that would leak existence across the privacy boundary."""
    s = two_clients_setup
    _login(client, **ADMIN)
    # Set Asha and Cara to share an email.
    client.patch(f"/candidates/{s['asha']}", json={"email": "shared@example.com"})
    client.patch(f"/candidates/{s['cara']}", json={"email": "shared@example.com"})
    client.post("/auth/logout")

    _login_as_acme_client(client)
    dups = client.get(f"/candidates/{s['asha']}/duplicates").json()
    # Cara matches by email but is invisible to Acme — should not appear.
    assert all(d["id"] != s["cara"] for d in dups)


# ----- bulk import requires target_job_id for clients ---------------------


def test_client_bulk_import_requires_target_job_id(
    client, two_clients_setup, fake_storage, captured_enqueue
):
    _login_as_acme_client(client)
    files = [("files", ("a.pdf", io.BytesIO(b"%PDF-1"), "application/pdf"))]
    r = client.post("/candidates/bulk-import", files=files)
    assert r.status_code == 400
    assert "target_job_id" in r.json()["detail"]


def test_client_bulk_import_other_clients_job_404(
    client, two_clients_setup, fake_storage, captured_enqueue
):
    _login_as_acme_client(client)
    files = [("files", ("a.pdf", io.BytesIO(b"%PDF-1"), "application/pdf"))]
    r = client.post(
        "/candidates/bulk-import",
        files=files,
        params={"target_job_id": two_clients_setup["globex_job"]["id"]},
    )
    assert r.status_code == 404


def test_client_bulk_import_auto_links_to_target_job(
    client, two_clients_setup, fake_storage, captured_enqueue, db_session
):
    s = two_clients_setup
    _login_as_acme_client(client)
    files = [("files", ("new.pdf", io.BytesIO(b"%PDF-1"), "application/pdf"))]
    r = client.post(
        "/candidates/bulk-import",
        files=files,
        params={"target_job_id": s["acme_job"]["id"]},
    )
    assert r.status_code == 201
    body = r.json()
    new_cid = body["results"][0]["candidate_id"]

    # New candidate is linked to acme_job
    from app.models.pipeline import CandidateJob

    db_session.expire_all()
    link = (
        db_session.query(CandidateJob)
        .filter_by(candidate_id=new_cid, job_id=s["acme_job"]["id"])
        .one_or_none()
    )
    assert link is not None
    # Created candidate is now visible to the client
    assert client.get(f"/candidates/{new_cid}").status_code == 200


def test_resume_uploaded_by_populated_in_single_upload(
    client, two_clients_setup, fake_storage, captured_enqueue, db_session
):
    s = two_clients_setup
    _login_as_acme_client(client)
    me = client.get("/auth/me").json()

    files = {"file": ("r.pdf", io.BytesIO(b"%PDF-1"), "application/pdf")}
    r = client.post(f"/candidates/{s['asha']}/resumes", files=files)
    assert r.status_code == 201
    rid = r.json()["id"]

    from app.models.resume import Resume

    db_session.expire_all()
    resume = db_session.get(Resume, rid)
    assert resume is not None
    assert resume.uploaded_by == me["id"]


def test_resume_uploaded_by_populated_in_bulk_import(
    client, two_clients_setup, fake_storage, captured_enqueue, db_session
):
    s = two_clients_setup
    _login_as_acme_client(client)
    me = client.get("/auth/me").json()

    files = [("files", ("a.pdf", io.BytesIO(b"%PDF-1"), "application/pdf"))]
    r = client.post(
        "/candidates/bulk-import",
        files=files,
        params={"target_job_id": s["acme_job"]["id"]},
    )
    rid = r.json()["results"][0]["resume_id"]

    from app.models.resume import Resume

    db_session.expire_all()
    resume = db_session.get(Resume, rid)
    assert resume is not None
    assert resume.uploaded_by == me["id"]


# ----- search + ask scoping -----------------------------------------------


def test_client_search_excludes_other_clients_candidates(
    client, two_clients_setup
):
    """Filter-only path (no q) should respect the visibility filter."""
    s = two_clients_setup
    _login_as_acme_client(client)
    r = client.post("/search/candidates", json={})
    assert r.status_code == 200
    ids = {hit["candidate"]["id"] for hit in r.json()}
    assert ids == {s["asha"], s["ben"]}


def test_client_ask_invisible_candidate_404(client, two_clients_setup):
    _login_as_acme_client(client)
    r = client.post(
        f"/ask/candidate/{two_clients_setup['cara']}",
        json={"question": "what?"},
    )
    assert r.status_code == 404


def test_client_blocked_from_admin_endpoints(client, two_clients_setup):
    _login_as_acme_client(client)
    assert client.post("/admin/reindex/candidates").status_code == 403
    assert client.get("/admin/audit-log").status_code == 403
    assert client.get("/admin/metrics").status_code == 403
    assert client.get("/users").status_code == 403


# ----- deleted-client lockout ---------------------------------------------


def test_deleted_client_locks_user_out(client, db_session):
    """If the client a client-role user is tagged to is deleted, current_user
    raises 401 — the user is effectively locked out until an admin re-tags."""
    _login(client, **ADMIN)
    cid = client.post("/clients", json={"name": "Doomed"}).json()["id"]
    client.post(
        "/users",
        json={
            "email": "doomed-hr@example.com",
            "name": "Doomed HR",
            "password": "doomed-pass-1",
            "role": "client",
            "client_id": cid,
        },
    )
    client.post("/auth/logout")

    # First: log in works
    r = client.post(
        "/auth/login",
        json={"email": "doomed-hr@example.com", "password": "doomed-pass-1"},
    )
    assert r.status_code == 200
    client.post("/auth/logout")

    # Admin nukes client_id directly (simulating ON DELETE SET NULL after
    # client deletion — we don't actually delete a client with users tagged
    # since clients can't be deleted while jobs exist in this fixture).
    from app.models.user import User

    user = db_session.query(User).filter_by(email="doomed-hr@example.com").one()
    user.client_id = None
    db_session.commit()

    # Now login still works (auth on email+password) but current_user blocks.
    r = client.post(
        "/auth/login",
        json={"email": "doomed-hr@example.com", "password": "doomed-pass-1"},
    )
    # Login succeeds (sets cookie) but the next protected call fails.
    # Note: login itself doesn't run current_user, so it returns 200 with the
    # set-cookie. The /auth/me check is what blocks.
    me = client.get("/auth/me")
    assert me.status_code == 401
