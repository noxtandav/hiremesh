import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import storage
from app.core.db import get_db
from app.core.deps import current_user
from app.models.candidate import Candidate
from app.models.resume import Resume
from app.models.user import User
from app.schemas.resumes import PresignedUrl, ResumeOut

router = APIRouter(tags=["resumes"])

ALLOWED_MIME: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/msword": ".doc",
}
MAX_BYTES = 10 * 1024 * 1024  # 10 MB


def _candidate_or_404(db: Session, candidate_id: int) -> Candidate:
    obj = db.get(Candidate, candidate_id)
    if obj is None or obj.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Candidate not found")
    return obj


def _resume_or_404(db: Session, resume_id: int) -> Resume:
    obj = db.get(Resume, resume_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Resume not found")
    return obj


def _enqueue_parse(resume_id: int) -> None:
    """Send the parse task to Celery. Decoupled so tests can monkeypatch it."""
    from app.workers.tasks.parse_resume import parse_resume

    parse_resume.delay(resume_id)


@router.post(
    "/candidates/{candidate_id}/resumes",
    response_model=ResumeOut,
    status_code=status.HTTP_201_CREATED,
    tags=["candidates"],
)
async def upload_resume(
    candidate_id: int,
    _user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
):
    _candidate_or_404(db, candidate_id)

    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Only PDF and DOCX are accepted (got {file.content_type})",
        )

    body = await file.read()
    if len(body) > MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "Resume must be 10 MB or smaller",
        )

    suffix = ALLOWED_MIME[file.content_type]
    s3_key = f"resumes/{candidate_id}/{uuid.uuid4().hex}{suffix}"
    storage.put_object(s3_key, body, file.content_type)

    # First resume becomes primary by default.
    has_existing = (
        db.scalar(
            select(Resume.id).where(Resume.candidate_id == candidate_id).limit(1)
        )
        is not None
    )

    resume = Resume(
        candidate_id=candidate_id,
        filename=file.filename or "resume",
        s3_key=s3_key,
        mime=file.content_type,
        is_primary=not has_existing,
        parse_status="pending",
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    _enqueue_parse(resume.id)
    return resume


@router.get(
    "/candidates/{candidate_id}/resumes",
    response_model=list[ResumeOut],
    tags=["candidates"],
)
def list_resumes(
    candidate_id: int,
    _user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    _candidate_or_404(db, candidate_id)
    return list(
        db.scalars(
            select(Resume)
            .where(Resume.candidate_id == candidate_id)
            .order_by(Resume.is_primary.desc(), Resume.created_at.desc())
        ).all()
    )


@router.post("/resumes/{resume_id}/primary", response_model=ResumeOut)
def set_primary(
    resume_id: int,
    _user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    resume = _resume_or_404(db, resume_id)
    db.execute(
        update(Resume)
        .where(Resume.candidate_id == resume.candidate_id)
        .values(is_primary=False)
    )
    resume.is_primary = True
    db.commit()
    db.refresh(resume)
    return resume


@router.get("/resumes/{resume_id}/url", response_model=PresignedUrl)
def get_download_url(
    resume_id: int,
    _user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    resume = _resume_or_404(db, resume_id)
    expires_in = 300
    return PresignedUrl(
        url=storage.presigned_get_url(resume.s3_key, expires_in=expires_in),
        expires_in=expires_in,
    )


@router.post("/resumes/{resume_id}/reparse", response_model=ResumeOut)
def reparse(
    resume_id: int,
    _user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    resume = _resume_or_404(db, resume_id)
    resume.parse_status = "pending"
    resume.parse_error = None
    db.commit()
    db.refresh(resume)
    _enqueue_parse(resume.id)
    return resume


@router.delete("/resumes/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_resume(
    resume_id: int,
    _user: Annotated[User, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    resume = _resume_or_404(db, resume_id)
    try:
        storage.delete_object(resume.s3_key)
    except Exception:  # noqa: BLE001 — best-effort; row removal still proceeds
        pass
    was_primary = resume.is_primary
    candidate_id = resume.candidate_id
    db.delete(resume)
    db.commit()

    # If we removed the primary, promote the most recent remaining resume.
    if was_primary:
        next_primary = db.scalar(
            select(Resume)
            .where(Resume.candidate_id == candidate_id)
            .order_by(Resume.created_at.desc())
            .limit(1)
        )
        if next_primary is not None:
            next_primary.is_primary = True
            db.commit()
