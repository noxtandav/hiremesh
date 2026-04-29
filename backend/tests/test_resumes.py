"""Resume upload + parse pipeline.

We stub `app.core.storage` (the S3 client) and inline the parse task instead
of going through Celery — that gives us full coverage of the upload → parse →
fields-applied → sticky-respected loop without needing MinIO or Redis.
"""

from __future__ import annotations

import io

import pytest

from app.api import resumes as resumes_api
from app.core import db as db_module
from app.core import storage
from app.services.candidates import get_overridden_fields
from app.workers.tasks import parse_resume as parse_task

ADMIN = {"email": "admin@example.com", "password": "admin-pass-12345"}


def _login(client, **creds):
    r = client.post("/auth/login", json=creds)
    assert r.status_code == 200, r.text


@pytest.fixture
def fake_storage(monkeypatch):
    """In-memory replacement for app.core.storage."""
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
    """Run parse_resume + embed_candidate synchronously instead of via Celery."""

    def _enqueue(resume_id: int) -> None:
        parse_task.parse_resume.run(resume_id)

    monkeypatch.setattr(resumes_api, "_enqueue_parse", _enqueue, raising=True)

    # parse_resume chains an embed_candidate task on success. There's no
    # Redis broker in tests, so route `.delay` to `.run`.
    from app.workers.tasks import embed_candidate as embed_task

    monkeypatch.setattr(
        embed_task.embed_candidate,
        "delay",
        lambda candidate_id: embed_task.embed_candidate.run(candidate_id),
        raising=True,
    )


def _resume_payload(name: str = "Asha Rao") -> bytes:
    return (
        f"{name}\nasha@example.com\n"
        "Skills: Python, FastAPI, Postgres, Kafka\n"
        "Worked at fintech companies for 6 years.\n"
    ).encode()


def test_upload_creates_resume_and_makes_first_primary(
    client, fake_storage, inline_parse
):
    _login(client, **ADMIN)
    cid = client.post("/candidates", json={"full_name": "Asha Rao"}).json()["id"]

    r = client.post(
        f"/candidates/{cid}/resumes",
        files={"file": ("asha.pdf", io.BytesIO(_resume_payload()), "application/pdf")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    rid = body["id"]
    assert body["filename"] == "asha.pdf"
    assert body["is_primary"] is True

    # The inline parser ran synchronously in a separate session. Read back to
    # observe the post-parse state.
    listed = {x["id"]: x for x in client.get(f"/candidates/{cid}/resumes").json()}
    assert listed[rid]["parse_status"] == "done"
    assert "Python" in listed[rid]["parsed_json"]["skills"]


def test_second_upload_is_not_primary(client, fake_storage, inline_parse):
    _login(client, **ADMIN)
    cid = client.post("/candidates", json={"full_name": "X"}).json()["id"]

    client.post(
        f"/candidates/{cid}/resumes",
        files={"file": ("a.pdf", io.BytesIO(_resume_payload()), "application/pdf")},
    )
    r2 = client.post(
        f"/candidates/{cid}/resumes",
        files={"file": ("b.pdf", io.BytesIO(_resume_payload()), "application/pdf")},
    )
    assert r2.json()["is_primary"] is False

    listed = client.get(f"/candidates/{cid}/resumes").json()
    primaries = [r for r in listed if r["is_primary"]]
    assert len(primaries) == 1


def test_set_primary_demotes_others(client, fake_storage, inline_parse):
    _login(client, **ADMIN)
    cid = client.post("/candidates", json={"full_name": "X"}).json()["id"]

    a = client.post(
        f"/candidates/{cid}/resumes",
        files={"file": ("a.pdf", io.BytesIO(b"x"), "application/pdf")},
    ).json()
    b = client.post(
        f"/candidates/{cid}/resumes",
        files={"file": ("b.pdf", io.BytesIO(b"x"), "application/pdf")},
    ).json()

    r = client.post(f"/resumes/{b['id']}/primary")
    assert r.status_code == 200
    assert r.json()["is_primary"] is True

    listed = {r["id"]: r["is_primary"] for r in client.get(f"/candidates/{cid}/resumes").json()}
    assert listed[a["id"]] is False
    assert listed[b["id"]] is True


def test_unsupported_mime_rejected(client, fake_storage):
    _login(client, **ADMIN)
    cid = client.post("/candidates", json={"full_name": "X"}).json()["id"]

    r = client.post(
        f"/candidates/{cid}/resumes",
        files={"file": ("a.txt", io.BytesIO(b"hi"), "text/plain")},
    )
    assert r.status_code == 415


def test_parsed_fields_applied_to_candidate(client, fake_storage, inline_parse):
    _login(client, **ADMIN)
    cid = client.post("/candidates", json={"full_name": "Placeholder"}).json()["id"]

    client.post(
        f"/candidates/{cid}/resumes",
        files={
            "file": (
                "asha.pdf",
                io.BytesIO(_resume_payload("Asha Rao")),
                "application/pdf",
            )
        },
    )

    after = client.get(f"/candidates/{cid}").json()
    assert after["full_name"] == "Asha Rao"
    assert after["email"] == "asha@example.com"
    assert "Python" in after["skills"]


def test_manual_edit_is_sticky_through_reparse(client, fake_storage, inline_parse):
    _login(client, **ADMIN)
    cid = client.post("/candidates", json={"full_name": "Placeholder"}).json()["id"]

    # Manual edit happens first.
    client.patch(f"/candidates/{cid}", json={"location": "Bangalore"})

    # Then a parse arrives that would set location to something else.
    payload = (
        b"Asha Rao\nasha@example.com\nLocation: Pune\n"
        b"Skills: Python, FastAPI\n"
    )
    rid = client.post(
        f"/candidates/{cid}/resumes",
        files={"file": ("asha.pdf", io.BytesIO(payload), "application/pdf")},
    ).json()["id"]

    after = client.get(f"/candidates/{cid}").json()
    assert after["location"] == "Bangalore"  # manual edit survives

    # Override is recorded
    with db_module.SessionLocal() as s:
        assert "location" in get_overridden_fields(s, cid)

    # Re-parsing again still respects the override
    client.post(f"/resumes/{rid}/reparse")
    assert client.get(f"/candidates/{cid}").json()["location"] == "Bangalore"


def test_presigned_url_endpoint(client, fake_storage, inline_parse):
    _login(client, **ADMIN)
    cid = client.post("/candidates", json={"full_name": "X"}).json()["id"]

    rid = client.post(
        f"/candidates/{cid}/resumes",
        files={"file": ("a.pdf", io.BytesIO(b"x"), "application/pdf")},
    ).json()["id"]

    r = client.get(f"/resumes/{rid}/url")
    assert r.status_code == 200
    body = r.json()
    assert body["url"].startswith("http://stub.test/resumes/")
    assert body["expires_in"] == 300


def test_stream_resume_file_returns_bytes_inline(client, fake_storage, inline_parse):
    _login(client, **ADMIN)
    cid = client.post("/candidates", json={"full_name": "X"}).json()["id"]

    body = b"%PDF-1.4 fake content"
    rid = client.post(
        f"/candidates/{cid}/resumes",
        files={"file": ("a.pdf", io.BytesIO(body), "application/pdf")},
    ).json()["id"]

    r = client.get(f"/resumes/{rid}/file")
    assert r.status_code == 200
    assert r.content == body
    assert r.headers["content-type"].startswith("application/pdf")
    assert "inline" in r.headers["content-disposition"]
    assert "a.pdf" in r.headers["content-disposition"]


def test_stream_resume_file_attachment_when_download(client, fake_storage, inline_parse):
    _login(client, **ADMIN)
    cid = client.post("/candidates", json={"full_name": "X"}).json()["id"]
    rid = client.post(
        f"/candidates/{cid}/resumes",
        files={"file": ("a.pdf", io.BytesIO(b"x"), "application/pdf")},
    ).json()["id"]

    r = client.get(f"/resumes/{rid}/file?download=true")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]


def test_stream_resume_file_unauthenticated(client, fake_storage, inline_parse):
    _login(client, **ADMIN)
    cid = client.post("/candidates", json={"full_name": "X"}).json()["id"]
    rid = client.post(
        f"/candidates/{cid}/resumes",
        files={"file": ("a.pdf", io.BytesIO(b"x"), "application/pdf")},
    ).json()["id"]
    client.post("/auth/logout")

    r = client.get(f"/resumes/{rid}/file")
    assert r.status_code == 401


def test_stream_resume_file_unknown_id(client, fake_storage):
    _login(client, **ADMIN)
    r = client.get("/resumes/99999/file")
    assert r.status_code == 404


def test_delete_resume_promotes_next_primary(client, fake_storage, inline_parse):
    _login(client, **ADMIN)
    cid = client.post("/candidates", json={"full_name": "X"}).json()["id"]

    a = client.post(
        f"/candidates/{cid}/resumes",
        files={"file": ("a.pdf", io.BytesIO(b"x"), "application/pdf")},
    ).json()
    b = client.post(
        f"/candidates/{cid}/resumes",
        files={"file": ("b.pdf", io.BytesIO(b"x"), "application/pdf")},
    ).json()
    assert a["is_primary"] is True
    assert b["is_primary"] is False

    assert client.delete(f"/resumes/{a['id']}").status_code == 204
    listed = client.get(f"/candidates/{cid}/resumes").json()
    assert len(listed) == 1
    assert listed[0]["id"] == b["id"]
    assert listed[0]["is_primary"] is True
