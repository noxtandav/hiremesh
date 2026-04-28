"""Operational audit log.

`record(...)` writes a row best-effort: it commits in its own subtransaction
if possible, and swallows exceptions so a logging hiccup never fails the
user's actual request. Audit is observability, not a security boundary.
"""

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog

log = logging.getLogger(__name__)


def record(
    db: Session,
    *,
    actor_id: int | None,
    action: str,
    entity: str,
    entity_id: int | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Insert an audit row.

    Uses a SAVEPOINT so failures here can't poison the caller's transaction.
    """
    try:
        with db.begin_nested():
            db.add(
                AuditLog(
                    actor_id=actor_id,
                    action=action,
                    entity=entity,
                    entity_id=entity_id,
                    payload=payload,
                )
            )
    except Exception:  # noqa: BLE001 — audit is best-effort
        log.exception("audit record failed: action=%s entity=%s", action, entity)
