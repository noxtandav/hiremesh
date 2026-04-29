"""Best-effort retrieval of a resume's full text.

Two consumers want the resume body as a string: per-candidate Q&A (so the
LLM can answer questions about anything in the resume) and the embedding
builder (so semantic search can match against the full content, not just
structured fields).

The fallback chain — `extracted_text` > re-extract from object storage >
`parsed_json["summary"]` — handles legacy resumes uploaded before the
`extracted_text` column existed, and gracefully degrades when storage is
temporarily unreachable.
"""

from __future__ import annotations

from app.models.resume import Resume


def get_resume_text(resume: Resume) -> str | None:
    if resume.extracted_text:
        return resume.extracted_text
    try:
        from app.core import storage
        from app.services.parsing import extract_text

        body = storage.get_object(resume.s3_key)
        text = extract_text(resume.filename, body)
        if text:
            return text
    except Exception:  # noqa: BLE001 — transient storage failures must not break callers
        pass
    if resume.parsed_json:
        summary = resume.parsed_json.get("summary")
        if isinstance(summary, str) and summary:
            return summary
    return None
