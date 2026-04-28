"""SQLAlchemy column type that uses pgvector on Postgres and falls back to
JSON on other backends (e.g. SQLite, used in unit tests).

The fallback isn't searchable with vector operators, but it lets the same
SQLAlchemy model work in tests without a real Postgres.
"""

from sqlalchemy import JSON, types

try:
    from pgvector.sqlalchemy import Vector as _PgVector
except ImportError:  # pragma: no cover - pgvector should always be installed
    _PgVector = None


class VectorColumn(types.TypeDecorator):
    impl = JSON
    cache_ok = True

    def __init__(self, dim: int, **kwargs):
        self.dim = dim
        super().__init__(**kwargs)

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql" and _PgVector is not None:
            return dialect.type_descriptor(_PgVector(self.dim))
        return dialect.type_descriptor(JSON())
