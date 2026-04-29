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


def test_duplicates_match_by_email_case_insensitive(client):
    _login(client, **ADMIN)
    a = client.post(
        "/candidates", json={"full_name": "Asha A", "email": "asha@example.com"}
    ).json()["id"]
    b = client.post(
        "/candidates", json={"full_name": "Asha B", "email": "ASHA@example.com"}
    ).json()["id"]

    dups_a = client.get(f"/candidates/{a}/duplicates").json()
    assert [d["id"] for d in dups_a] == [b]
    dups_b = client.get(f"/candidates/{b}/duplicates").json()
    assert [d["id"] for d in dups_b] == [a]


def test_duplicates_match_by_phone(client):
    _login(client, **ADMIN)
    a = client.post(
        "/candidates", json={"full_name": "X", "phone": "+91-9999-99999"}
    ).json()["id"]
    b = client.post(
        "/candidates", json={"full_name": "Y", "phone": "+91-9999-99999"}
    ).json()["id"]
    other = client.post(
        "/candidates", json={"full_name": "Z", "phone": "+1-555-0000"}
    ).json()["id"]

    dups = {d["id"] for d in client.get(f"/candidates/{a}/duplicates").json()}
    assert dups == {b}
    assert other not in dups


def test_duplicates_empty_when_no_email_or_phone(client):
    _login(client, **ADMIN)
    cid = client.post("/candidates", json={"full_name": "Nobody"}).json()["id"]
    client.post("/candidates", json={"full_name": "Also Nobody"})
    assert client.get(f"/candidates/{cid}/duplicates").json() == []


def test_duplicates_excludes_self_and_soft_deleted(client):
    _login(client, **ADMIN)
    keep = client.post(
        "/candidates", json={"full_name": "Keep", "email": "dup@example.com"}
    ).json()["id"]
    gone = client.post(
        "/candidates", json={"full_name": "Gone", "email": "dup@example.com"}
    ).json()["id"]
    client.delete(f"/candidates/{gone}")

    dups = client.get(f"/candidates/{keep}/duplicates").json()
    assert dups == []  # self excluded, soft-deleted excluded


def test_duplicates_404_for_unknown_candidate(client):
    _login(client, **ADMIN)
    r = client.get("/candidates/99999/duplicates")
    assert r.status_code == 404


def test_created_by_set_on_creation(client):
    _login(client, **ADMIN)
    me = client.get("/auth/me").json()
    cid = client.post(
        "/candidates", json={"full_name": "With Owner"}
    ).json()["id"]

    detail = client.get(f"/candidates/{cid}").json()
    assert detail["created_by"] == me["id"]
    assert detail["created_by_name"] == me["name"]


def test_created_by_hydrates_recruiter_name(client):
    _login(client, **ADMIN)
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
    client.post(
        "/auth/login", json={"email": "rec@example.com", "password": "rec-pass-12345"}
    )

    cid = client.post(
        "/candidates", json={"full_name": "By Recruiter"}
    ).json()["id"]
    detail = client.get(f"/candidates/{cid}").json()
    assert detail["created_by_name"] == "Rec One"


def test_list_endpoint_does_not_hydrate_creator_name(client):
    """List view skips the per-row name lookup. It still exposes created_by
    (the int id) so a UI that wants names can choose to fan out."""
    _login(client, **ADMIN)
    me = client.get("/auth/me").json()
    client.post("/candidates", json={"full_name": "A"})
    client.post("/candidates", json={"full_name": "B"})

    rows = client.get("/candidates").json()
    assert all(r["created_by"] == me["id"] for r in rows)
    assert all(r["created_by_name"] is None for r in rows)


def test_bulk_import_records_creator(client, fake_storage, captured_enqueue):
    _login(client, **ADMIN)
    me = client.get("/auth/me").json()
    files = [
        ("files", ("asha.pdf", io.BytesIO(b"%PDF-fake"), "application/pdf")),
        ("files", ("ben.pdf", io.BytesIO(b"%PDF-fake2"), "application/pdf")),
    ]
    body = client.post("/candidates/bulk-import", files=files).json()

    for r in body["results"]:
        if r["status"] == "ok":
            detail = client.get(f"/candidates/{r['candidate_id']}").json()
            assert detail["created_by"] == me["id"]
            assert detail["created_by_name"] == me["name"]


def test_bulk_import_writes_per_candidate_audit_rows(client, fake_storage, captured_enqueue):
    _login(client, **ADMIN)
    files = [
        ("files", ("a.pdf", io.BytesIO(b"%PDF-1"), "application/pdf")),
        ("files", ("b.pdf", io.BytesIO(b"%PDF-2"), "application/pdf")),
    ]
    client.post("/candidates/bulk-import", files=files)

    rows = client.get(
        "/admin/audit-log", params={"action": "candidate.create"}
    ).json()
    via_bulk = [r for r in rows if r.get("payload", {}).get("via") == "bulk_import"]
    assert len(via_bulk) == 2
    assert all(r["entity"] == "candidate" for r in via_bulk)
    assert all(r["entity_id"] is not None for r in via_bulk)


# Fixtures borrowed from test_bulk_import.py — duplicated here to keep
# tests independent. The shared fixture pattern would need a conftest
# refactor that's out of scope for this addition.
import io  # noqa: E402

import pytest  # noqa: E402

from app.api import resumes as resumes_api  # noqa: E402
from app.core import storage  # noqa: E402
from app.workers.tasks import parse_resume as parse_task  # noqa: E402


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

