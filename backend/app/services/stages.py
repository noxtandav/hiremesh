from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.stage_template import StageTemplate
from app.schemas.stages import StageInput

DEFAULT_STAGES: list[str] = [
    "Sourced/Teaser",
    "InMail to be sent",
    "Email cadence initiated",
    "InMail sent",
    "Follow-Up",
    "Not Interested",
    "Interested",
    "Submitted",
]


def list_template(db: Session) -> list[StageTemplate]:
    return list(
        db.scalars(select(StageTemplate).order_by(StageTemplate.position)).all()
    )


def seed_default_template_if_needed(db: Session) -> int:
    """Idempotent: seeds the 8 default stages only if the table is empty."""
    if db.scalar(select(StageTemplate).limit(1)) is not None:
        return 0
    for i, name in enumerate(DEFAULT_STAGES):
        db.add(StageTemplate(name=name, position=i))
    db.commit()
    return len(DEFAULT_STAGES)


def replace_template(db: Session, stages: list[StageInput]) -> list[StageTemplate]:
    """Replace the template wholesale.

    Stages with an `id` are kept (and renamed/repositioned in-place); stages
    without an `id` are inserted; existing rows whose id isn't in the payload
    are deleted. Position is taken from list order.
    """
    existing = {s.id: s for s in list_template(db)}
    keep_ids: set[int] = set()
    new_rows: list[StageTemplate] = []

    for position, item in enumerate(stages):
        if item.id is not None and item.id in existing:
            row = existing[item.id]
            row.name = item.name
            row.position = position
            keep_ids.add(item.id)
            new_rows.append(row)
        else:
            row = StageTemplate(name=item.name, position=position)
            db.add(row)
            new_rows.append(row)

    drop_ids = [sid for sid in existing if sid not in keep_ids]
    if drop_ids:
        db.execute(delete(StageTemplate).where(StageTemplate.id.in_(drop_ids)))

    db.commit()
    return list_template(db)
