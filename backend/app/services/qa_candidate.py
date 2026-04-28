"""Per-candidate Q&A.

Builds a context document from the candidate's profile + primary resume +
all notes, asks the configured Q&A model, and returns the answer with
citations pointing at specific resume / note rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import llm
from app.models.candidate import Candidate
from app.models.note import Note
from app.models.resume import Resume


@dataclass
class Citation:
    type: Literal["profile", "resume", "note"]
    id: int | None  # null for the synthetic 'profile' citation
    snippet: str

    def to_dict(self) -> dict:
        return {"type": self.type, "id": self.id, "snippet": self.snippet}


def _gather_context(
    db: Session, candidate: Candidate
) -> tuple[str, list[Citation]]:
    """Stitch together a single context string, returning a parallel list of
    citations the LLM can refer to by source id."""
    blocks: list[str] = []
    citations: list[Citation] = []

    # Profile block (always citation id=None)
    profile_lines = [f"Name: {candidate.full_name}"]
    for label, val in [
        ("Email", candidate.email),
        ("Phone", candidate.phone),
        ("Location", candidate.location),
        ("Current title", candidate.current_title),
        ("Current company", candidate.current_company),
        ("Total experience (years)", candidate.total_exp_years),
        ("Current CTC", candidate.current_ctc),
        ("Expected CTC", candidate.expected_ctc),
        ("Notice period (days)", candidate.notice_period_days),
    ]:
        if val is not None:
            profile_lines.append(f"{label}: {val}")
    if candidate.skills:
        profile_lines.append("Skills: " + ", ".join(candidate.skills))
    if candidate.summary:
        profile_lines.append(f"Summary: {candidate.summary}")
    profile_text = "\n".join(profile_lines)
    blocks.append(f"[PROFILE]\n{profile_text}")
    citations.append(
        Citation(type="profile", id=None, snippet=profile_text[:200])
    )

    # Primary resume's parsed text
    primary = db.scalar(
        select(Resume)
        .where(
            Resume.candidate_id == candidate.id,
            Resume.is_primary.is_(True),
        )
        .limit(1)
    )
    if primary is not None and primary.parsed_json:
        body = primary.parsed_json.get("summary") or ""
        if body:
            blocks.append(f"[RESUME #{primary.id}]\n{body}")
            citations.append(
                Citation(type="resume", id=primary.id, snippet=body[:240])
            )

    # All notes (global + link-scoped) — most recent first
    notes = list(
        db.scalars(
            select(Note)
            .where(Note.candidate_id == candidate.id)
            .order_by(Note.created_at.desc())
        ).all()
    )
    for n in notes:
        scope = "link" if n.candidate_job_id else "global"
        blocks.append(f"[NOTE #{n.id} · {scope}]\n{n.body}")
        citations.append(Citation(type="note", id=n.id, snippet=n.body[:240]))

    return "\n\n".join(blocks), citations


_PROMPT_SYSTEM = (
    "You answer questions about a single recruitment candidate using ONLY the "
    "context provided. Be concise and factual. If the answer is not in the "
    "context, say so explicitly — do not guess. When you reference information "
    "from the context, cite the source by its bracketed tag, e.g. [RESUME #3] "
    "or [NOTE #12]."
)


def _fake_answer(question: str, context: str) -> str:
    """Deterministic dev-mode answer.

    Searches the context for question keywords (>=4 chars) and returns the
    surrounding text. Good enough to demo the Q&A loop without an API key.
    """
    import re

    keywords = [
        w.lower() for w in re.findall(r"[A-Za-z]{4,}", question)
    ]
    if not keywords:
        return "I don't have enough to answer that from the context."
    found_lines: list[str] = []
    for line in context.splitlines():
        low = line.lower()
        if any(k in low for k in keywords):
            found_lines.append(line.strip())
    if not found_lines:
        return (
            "I couldn't find anything matching that in the context. "
            "Try rephrasing."
        )
    return "Based on the context:\n" + "\n".join(f"- {l}" for l in found_lines[:6])


def answer_for_candidate(
    db: Session, candidate: Candidate, question: str
) -> dict:
    context, citations = _gather_context(db, candidate)
    if llm.qa_is_fake():
        answer = _fake_answer(question, context)
    else:
        answer = llm.qa_complete(
            system=_PROMPT_SYSTEM,
            user=f"Context:\n---\n{context}\n---\n\nQuestion: {question}",
        )
    return {
        "answer": answer,
        "citations": [c.to_dict() for c in citations],
    }
