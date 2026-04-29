"""Bulk-import endpoint: many resumes in one request.

Each file becomes its own candidate; per-file errors don't kill the batch.
"""

from __future__ import annotations

import io

import pytest

from app.api import resumes as resumes_api
from app.core import storage
from app.workers.tasks import parse_resume as parse_task

ADMIN = {"email": "admin@example.com", "password": "admin-pass-12345"}

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


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
def inline_parse(monkeypatch):
    def _enqueue(resume_id: int) -> None:
        parse_task.parse_resume.run(resume_id)

    monkeypatch.setattr(resumes_api, "_enqueue_parse", _enqueue, raising=True)

    from app.workers.tasks import embed_candidate as embed_task

    monkeypatch.setattr(
        embed_task.embed_candidate,
        "delay",
        lambda candidate_id: embed_task.embed_candidate.run(candidate_id),
        raising=True,
    )


@pytest.fixture
def captured_enqueue(monkeypatch):
    """Capture enqueued resume IDs without running the parser."""
    captured: list[int] = []
    monkeypatch.setattr(
        resumes_api, "_enqueue_parse", lambda rid: captured.append(rid), raising=True
    )
    return captured


def _resume_payload(name: str = "Asha Rao") -> bytes:
    return (
        f"{name}\n{name.split()[0].lower()}@example.com\n"
        "Skills: Python, FastAPI, Postgres\n"
        "Worked at fintech companies for 6 years.\n"
    ).encode()


def test_bulk_import_creates_candidate_per_file(
    client, fake_storage, captured_enqueue
):
    _login(client, **ADMIN)

    files = [
        ("files", ("asha_rao.pdf", io.BytesIO(_resume_payload("Asha Rao")), PDF)),
        ("files", ("ben-shah.docx", io.BytesIO(_resume_payload("Ben Shah")), DOCX)),
    ]
    r = client.post("/candidates/bulk-import", files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["imported"] == 2
    assert body["total"] == 2
    assert len(body["results"]) == 2
    assert all(x["status"] == "ok" for x in body["results"])

    placeholders = {x["placeholder_name"] for x in body["results"]}
    assert placeholders == {"asha rao", "ben shah"}

    listed = client.get("/candidates").json()
    assert len(listed) == 2
    assert len(captured_enqueue) == 2

    for result in body["results"]:
        resumes = client.get(f"/candidates/{result['candidate_id']}/resumes").json()
        assert len(resumes) == 1
        assert resumes[0]["is_primary"] is True
        assert resumes[0]["parse_status"] == "pending"


def test_bulk_import_partial_failure_does_not_abort_batch(
    client, fake_storage, captured_enqueue
):
    _login(client, **ADMIN)

    files = [
        ("files", ("good.pdf", io.BytesIO(_resume_payload()), PDF)),
        ("files", ("bad.txt", io.BytesIO(b"hello"), "text/plain")),
        ("files", ("also-good.docx", io.BytesIO(_resume_payload("Two")), DOCX)),
    ]
    r = client.post("/candidates/bulk-import", files=files)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["imported"] == 2
    assert body["total"] == 3

    statuses = [x["status"] for x in body["results"]]
    assert statuses == ["ok", "error", "ok"]
    assert "Unsupported" in body["results"][1]["error"]

    assert len(client.get("/candidates").json()) == 2
    assert len(captured_enqueue) == 2


def test_bulk_import_rejects_oversize_per_file(
    client, fake_storage, captured_enqueue
):
    _login(client, **ADMIN)
    big = b"x" * (10 * 1024 * 1024 + 1)
    files = [
        ("files", ("ok.pdf", io.BytesIO(_resume_payload()), PDF)),
        ("files", ("huge.pdf", io.BytesIO(big), PDF)),
    ]
    r = client.post("/candidates/bulk-import", files=files)
    assert r.status_code == 201
    body = r.json()
    assert body["imported"] == 1
    assert body["results"][1]["status"] == "error"
    assert "10 MB" in body["results"][1]["error"]


def test_bulk_import_rejects_empty_file(client, fake_storage, captured_enqueue):
    _login(client, **ADMIN)
    files = [
        ("files", ("empty.pdf", io.BytesIO(b""), PDF)),
    ]
    r = client.post("/candidates/bulk-import", files=files)
    assert r.status_code == 201
    body = r.json()
    assert body["imported"] == 0
    assert body["results"][0]["status"] == "error"
    assert "empty" in body["results"][0]["error"].lower()


def test_bulk_import_no_files_returns_400(client, fake_storage):
    _login(client, **ADMIN)
    # Posting with no files at all → FastAPI rejects with 422 (missing field)
    r = client.post("/candidates/bulk-import")
    assert r.status_code in (400, 422)


def test_bulk_import_runs_parser_and_fills_real_names(
    client, fake_storage, inline_parse
):
    _login(client, **ADMIN)
    files = [
        ("files", ("placeholder.pdf", io.BytesIO(_resume_payload("Asha Rao")), PDF)),
    ]
    r = client.post("/candidates/bulk-import", files=files)
    assert r.status_code == 201
    cid = r.json()["results"][0]["candidate_id"]

    after = client.get(f"/candidates/{cid}").json()
    # Parser overwrote the filename-derived placeholder with the real name.
    assert after["full_name"] == "Asha Rao"
    assert after["email"] == "asha@example.com"
    assert "Python" in after["skills"]


def test_bulk_import_requires_auth(client):
    files = [
        ("files", ("a.pdf", io.BytesIO(b"x"), PDF)),
    ]
    r = client.post("/candidates/bulk-import", files=files)
    assert r.status_code == 401
