"""Admin CLI: argparse entrypoints in app/cli.py.

We invoke the cmd_* helpers directly with built argparse Namespaces so we
don't have to spawn a subprocess. SessionLocal is monkeypatched to the
test session-maker via the standard `client` fixture pattern.
"""

from __future__ import annotations

import argparse

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.cli import cmd_create, cmd_list, cmd_set_password
from app.core import db as db_module
from app.core.db import Base
from app.core.security import verify_password
from app.models.user import User


@pytest.fixture
def cli_db(monkeypatch):
    """Fresh in-memory DB exposed via the same SessionLocal the CLI reads."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng)
    TestSessionLocal = sessionmaker(
        bind=eng, autoflush=False, autocommit=False, future=True
    )
    monkeypatch.setattr(db_module, "engine", eng, raising=True)
    monkeypatch.setattr(db_module, "SessionLocal", TestSessionLocal, raising=True)
    yield TestSessionLocal
    Base.metadata.drop_all(eng)
    eng.dispose()


def _ns(**kwargs) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def test_cli_creates_admin(cli_db):
    cmd_create(
        _ns(
            email="boot@example.com",
            name="Bootstrap Admin",
            role="admin",
            password="long-enough-pw-1",
        )
    )
    with cli_db() as s:
        u = s.scalar(select(User).where(User.email == "boot@example.com"))
        assert u is not None
        assert u.role == "admin"
        assert u.is_active is True
        assert u.must_change_password is False
        assert verify_password("long-enough-pw-1", u.password_hash)


def test_cli_create_normalizes_email(cli_db):
    cmd_create(
        _ns(
            email="  Mixed@Example.COM  ",
            name="X",
            role="admin",
            password="long-enough-pw-1",
        )
    )
    with cli_db() as s:
        assert s.scalar(select(User).where(User.email == "mixed@example.com")) is not None


def test_cli_create_rejects_duplicate(cli_db):
    cmd_create(
        _ns(email="dup@example.com", name="X", role="admin", password="long-enough-pw-1")
    )
    with pytest.raises(SystemExit) as exc:
        cmd_create(
            _ns(email="dup@example.com", name="Y", role="admin", password="long-enough-pw-1")
        )
    assert "already exists" in str(exc.value)


def test_cli_create_rejects_short_password(cli_db):
    with pytest.raises(SystemExit) as exc:
        cmd_create(_ns(email="x@example.com", name="X", role="admin", password="short"))
    assert "12 characters" in str(exc.value)


def test_cli_set_password_updates_existing(cli_db):
    cmd_create(
        _ns(email="rotate@example.com", name="X", role="admin", password="initial-pw-12345")
    )
    cmd_set_password(_ns(email="rotate@example.com", password="new-password-123"))
    with cli_db() as s:
        u = s.scalar(select(User).where(User.email == "rotate@example.com"))
        assert u is not None
        assert verify_password("new-password-123", u.password_hash)
        assert not verify_password("initial-pw-12345", u.password_hash)


def test_cli_set_password_unknown_email(cli_db):
    with pytest.raises(SystemExit) as exc:
        cmd_set_password(_ns(email="nobody@example.com", password="long-enough-pw-1"))
    assert "No user" in str(exc.value)


def test_cli_set_password_reactivates_inactive(cli_db):
    cmd_create(
        _ns(email="off@example.com", name="X", role="admin", password="initial-pw-12345")
    )
    with cli_db() as s:
        u = s.scalar(select(User).where(User.email == "off@example.com"))
        assert u is not None
        u.is_active = False
        s.commit()

    cmd_set_password(_ns(email="off@example.com", password="new-password-123"))
    with cli_db() as s:
        u = s.scalar(select(User).where(User.email == "off@example.com"))
        assert u is not None
        assert u.is_active is True


def test_cli_list_when_empty(cli_db, capsys):
    cmd_list(_ns())
    out = capsys.readouterr().out
    assert "no admins exist" in out


def test_cli_list_shows_admins(cli_db, capsys):
    cmd_create(
        _ns(email="a@example.com", name="A", role="admin", password="long-enough-pw-1")
    )
    cmd_create(
        _ns(email="b@example.com", name="B", role="recruiter", password="long-enough-pw-1")
    )
    capsys.readouterr()  # discard create output
    cmd_list(_ns())
    out = capsys.readouterr().out
    assert "a@example.com" in out
    # Recruiters aren't listed (the command targets admins only).
    assert "b@example.com" not in out
