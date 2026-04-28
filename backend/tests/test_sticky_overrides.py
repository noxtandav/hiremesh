"""Sticky-edit invariant: parsed fields never overwrite manually-edited ones."""

from app.models.candidate import Candidate
from app.models.resume import CandidateFieldOverride
from app.services.candidates import (
    apply_manual_edit,
    apply_parsed_fields,
    get_overridden_fields,
)

ADMIN = {"email": "admin@example.com", "password": "admin-pass-12345"}


def _make_candidate(db_session, **kwargs) -> Candidate:
    c = Candidate(full_name=kwargs.pop("full_name", "Test"), skills=[], **kwargs)
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


def test_manual_edit_records_override(db_session):
    c = _make_candidate(db_session)
    apply_manual_edit(db_session, c, {"location": "Pune"}, set_by=None)
    db_session.commit()

    overrides = get_overridden_fields(db_session, c.id)
    assert "location" in overrides
    assert c.location == "Pune"


def test_parser_applies_only_non_overridden_fields(db_session):
    c = _make_candidate(db_session)
    apply_manual_edit(db_session, c, {"location": "Bangalore"}, set_by=None)
    db_session.commit()

    parsed = {
        "location": "Hyderabad",  # should be ignored — manual edit wins
        "current_title": "Backend Engineer",  # should apply
        "skills": ["Python", "Postgres"],  # should apply
        "phone": None,  # should be skipped (None)
        "summary": "",  # should apply (empty string is a valid value)
    }
    applied = apply_parsed_fields(db_session, c, parsed)
    db_session.commit()

    assert "location" not in applied
    assert "current_title" in applied
    assert "skills" in applied
    assert "phone" not in applied

    db_session.refresh(c)
    assert c.location == "Bangalore"  # untouched
    assert c.current_title == "Backend Engineer"
    assert c.skills == ["Python", "Postgres"]


def test_parser_skips_empty_lists_so_it_cannot_blank_skills(db_session):
    c = _make_candidate(db_session)
    c.skills = ["existing"]
    db_session.commit()

    apply_parsed_fields(db_session, c, {"skills": []})
    db_session.commit()
    db_session.refresh(c)
    assert c.skills == ["existing"]


def test_re_editing_an_overridden_field_updates_set_at(db_session):
    c = _make_candidate(db_session)
    apply_manual_edit(db_session, c, {"location": "Pune"}, set_by=None)
    db_session.commit()
    first = db_session.get(CandidateFieldOverride, (c.id, "location")).set_at

    apply_manual_edit(db_session, c, {"location": "Mumbai"}, set_by=None)
    db_session.commit()
    second = db_session.get(CandidateFieldOverride, (c.id, "location")).set_at

    assert second >= first
    assert c.location == "Mumbai"


def test_patch_endpoint_writes_overrides(client):
    r = client.post("/auth/login", json=ADMIN)
    assert r.status_code == 200

    cid = client.post("/candidates", json={"full_name": "Edit Me"}).json()["id"]

    client.patch(f"/candidates/{cid}", json={"location": "Pune", "summary": "Hand-written"})

    # Verify by reading the override table (round-trip via the worker test helper)
    from app.core.db import SessionLocal

    with SessionLocal() as s:
        overridden = get_overridden_fields(s, cid)
    assert "location" in overridden
    assert "summary" in overridden
