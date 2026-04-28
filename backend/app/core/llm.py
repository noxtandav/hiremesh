"""Thin wrapper around LiteLLM. Each task picks its model via env var.

Right now only resume parsing uses this. Future roles (embeddings, per-candidate
Q&A, pool Q&A classifier/SQL/synthesis) will read their own LLM_*_MODEL env vars
and call into the same `complete_json` helper.

Set `LLM_PARSE_MODEL=fake` to bypass any real LLM and use deterministic dummy
output — useful for dev and tests without API credentials.
"""

import json
import re
from typing import Any

from app.core.config import get_settings


def _is_fake() -> bool:
    return get_settings().llm_parse_model.lower() == "fake"


def _fake_parse_resume(text: str) -> dict[str, Any]:
    """Deterministic parse used when LLM_PARSE_MODEL=fake.

    Pulls a name and email out of the text by regex; everything else is left
    blank or set to a recognizable sentinel value so the dev can see the
    pipeline working end-to-end.
    """
    email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    email = email_match.group(0) if email_match else None

    # First non-empty line that looks like a name (no @, no http)
    name = None
    for line in (l.strip() for l in text.splitlines()):
        if line and "@" not in line and "http" not in line.lower() and len(line) < 80:
            name = line
            break
    name = name or "Unknown Candidate"

    skills_match = re.search(r"(?:skills?|technolog\w+)\s*[:\-]?\s*(.{0,200})", text, re.I)
    skills_blob = skills_match.group(1) if skills_match else ""
    skills = [
        s.strip()
        for s in re.split(r"[,;\n•·]", skills_blob)
        if 1 < len(s.strip()) < 30
    ][:8]

    return {
        "full_name": name,
        "email": email,
        "phone": None,
        "location": None,
        "current_company": None,
        "current_title": None,
        "total_exp_years": None,
        "current_ctc": None,
        "expected_ctc": None,
        "notice_period_days": None,
        "skills": skills,
        "summary": text[:400] if text else None,
    }


PARSE_PROMPT = """\
You are a resume parser. Extract the structured information below from the
resume text and return ONLY valid JSON matching the schema. Use null for
unknown values; do not invent. Skills should be a short list of canonical
technical or domain terms (no full sentences).

Schema:
{
  "full_name": string,
  "email": string | null,
  "phone": string | null,
  "location": string | null,
  "current_company": string | null,
  "current_title": string | null,
  "total_exp_years": number | null,
  "current_ctc": number | null,
  "expected_ctc": number | null,
  "notice_period_days": number | null,
  "skills": string[],
  "summary": string | null
}

Resume:
---
{TEXT}
---
"""


def parse_resume_text(text: str) -> dict[str, Any]:
    """Run resume text through the configured parser model and return a dict.

    The dict is unvalidated here — `apply_parsed_fields` decides which fields
    to actually write.
    """
    if _is_fake():
        return _fake_parse_resume(text)

    # Real path: LiteLLM with JSON-mode response.
    import litellm  # local import to keep startup fast in `fake` mode

    s = get_settings()
    kwargs: dict = {
        "model": s.llm_parse_model,
        "messages": [{"role": "user", "content": PARSE_PROMPT.replace("{TEXT}", text)}],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    # Pass api_key only when set; otherwise LiteLLM reads the right provider
    # env var (OPENROUTER_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.).
    if s.llm_api_key:
        kwargs["api_key"] = s.llm_api_key

    response = litellm.completion(**kwargs)
    content = response["choices"][0]["message"]["content"]
    return json.loads(content)


# ----- Q&A helpers ------------------------------------------------------


def qa_is_fake() -> bool:
    return get_settings().llm_qa_model.lower() == "fake"


def qa_complete(
    system: str,
    user: str,
    *,
    json_mode: bool = False,
    temperature: float = 0.2,
) -> str:
    """One-shot chat completion via the configured Q&A model.

    Returns the raw text content. For fake mode the caller is responsible —
    qa_complete just raises so we don't accidentally hit the network in fake
    mode. Use the dedicated `_fake_*` helpers in app/services/qa.py instead.
    """
    if qa_is_fake():
        raise RuntimeError(
            "qa_complete called in fake mode; use the fake helpers in services/qa.py"
        )

    import litellm

    s = get_settings()
    kwargs: dict = {
        "model": s.llm_qa_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if s.llm_api_key:
        kwargs["api_key"] = s.llm_api_key

    response = litellm.completion(**kwargs)
    return response["choices"][0]["message"]["content"]
