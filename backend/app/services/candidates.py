"""Candidate field write paths.

Two callers update a candidate's structured fields:

1. The PATCH /candidates/{id} endpoint (manual edit). Anything written here
   is **sticky** — recorded in candidate_field_overrides — so re-parsing a
   resume cannot stomp it.
2. The parse_resume worker. It writes only fields that are NOT in the
   overrides table; the rest are kept as-is.

Both go through the helpers below so the invariant lives in one place.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.candidate import Candidate
from app.models.resume import CandidateFieldOverride

# Fields the parser is allowed to fill. Add to this list when extending the
# resume schema. Anything outside it is ignored.
PARSEABLE_FIELDS: tuple[str, ...] = (
    "full_name",
    "email",
    "phone",
    "location",
    "current_company",
    "current_title",
    "total_exp_years",
    "current_ctc",
    "expected_ctc",
    "notice_period_days",
    "skills",
    "summary",
)


def get_overridden_fields(db: Session, candidate_id: int) -> set[str]:
    rows = db.scalars(
        select(CandidateFieldOverride.field_name).where(
            CandidateFieldOverride.candidate_id == candidate_id
        )
    ).all()
    return set(rows)


def apply_manual_edit(
    db: Session, candidate: Candidate, changes: dict[str, Any], set_by: int | None
) -> None:
    """Apply a manual PATCH to a candidate and record overrides for each field.

    Only commits the override marker, not the candidate row itself — leave the
    transaction handling to the caller (consistent with how the rest of the
    codebase works).
    """
    if not changes:
        return
    overridden = get_overridden_fields(db, candidate.id)
    for field, value in changes.items():
        setattr(candidate, field, value)
        if field not in overridden:
            db.add(
                CandidateFieldOverride(
                    candidate_id=candidate.id,
                    field_name=field,
                    set_by=set_by,
                    set_at=datetime.now(UTC),
                )
            )
            overridden.add(field)
        else:
            # Touch set_by/set_at so we know when it last moved.
            row = db.get(
                CandidateFieldOverride, (candidate.id, field)
            )
            if row is not None:
                row.set_by = set_by
                row.set_at = datetime.now(UTC)


def apply_parsed_fields(
    db: Session, candidate: Candidate, parsed: dict[str, Any]
) -> list[str]:
    """Write parsed fields to the candidate, skipping any that are overridden.

    Returns the list of fields actually applied. Fields whose parsed value is
    `None` or an empty list are skipped (parsing failures shouldn't blank
    out previously-good data).
    """
    overridden = get_overridden_fields(db, candidate.id)
    applied: list[str] = []
    for field in PARSEABLE_FIELDS:
        if field in overridden:
            continue
        if field not in parsed:
            continue
        new_value = parsed[field]
        if new_value is None:
            continue
        if isinstance(new_value, list) and not new_value:
            continue
        setattr(candidate, field, new_value)
        applied.append(field)
    return applied
