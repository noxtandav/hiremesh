import os

os.environ.setdefault("ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-prod-use-only")

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import db as db_module
from app.core.config import get_settings
from app.core.db import Base
from app.core.security import hash_password
from app.main import app
from app.models.user import User

# The fixed admin every test logs in as. Production has no env-based bootstrap
# (see app/cli.py); tests fabricate this row directly.
TEST_ADMIN_EMAIL = "admin@example.com"
TEST_ADMIN_PASSWORD = "admin-pass-12345"


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def db_session(engine) -> Generator[Session, None, None]:
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with TestSessionLocal() as s:
        yield s


@pytest.fixture
def client(engine, monkeypatch) -> Generator[TestClient, None, None]:
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    monkeypatch.setattr(db_module, "engine", engine, raising=True)
    monkeypatch.setattr(db_module, "SessionLocal", TestSessionLocal, raising=True)

    # Seed the admin every test logs in as. The app no longer bootstraps an
    # admin from env vars at startup (that was a prod footgun) — the operator
    # creates the first admin via app/cli.py post-deploy.
    with TestSessionLocal() as s:
        s.add(
            User(
                email=TEST_ADMIN_EMAIL,
                name="Admin",
                password_hash=hash_password(TEST_ADMIN_PASSWORD),
                role="admin",
                must_change_password=False,
                is_active=True,
            )
        )
        s.commit()

    def override_get_db():
        with TestSessionLocal() as s:
            yield s

    app.dependency_overrides[db_module.get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
