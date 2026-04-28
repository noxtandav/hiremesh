"""Pure parsing helpers — no Celery, no DB, easy to unit-test.

The Celery task in app.workers.tasks.parse_resume orchestrates these.
"""

import io


def extract_text(filename: str, body: bytes) -> str:
    """Best-effort text extraction from PDF or DOCX bytes.

    Falls back to UTF-8 decode if the typed extractor fails (e.g. corrupt PDF).
    The parser LLM is robust to a bit of noise, so partial recovery beats a
    hard failure.
    """
    lower = filename.lower()
    try:
        if lower.endswith(".pdf"):
            text = _extract_pdf(body)
            if text:
                return text
        elif lower.endswith(".docx") or lower.endswith(".doc"):
            text = _extract_docx(body)
            if text:
                return text
    except Exception:  # noqa: BLE001 — fall through to decode
        pass
    try:
        return body.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return ""


def _extract_pdf(body: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(body))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            continue
    return "\n".join(parts).strip()


def _extract_docx(body: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(body))
    return "\n".join(p.text for p in doc.paragraphs).strip()
