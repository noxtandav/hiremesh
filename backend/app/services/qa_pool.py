"""Pool Q&A: classify the question, route to the right path, synthesize.

Three routes:
- `structured`  — count/aggregate questions; LLM emits a StructuredQuery,
                  we run it against `v_candidate_search`, summarize the rows.
- `semantic`    — fuzzy questions; vector search (M4) gives top-k candidates;
                  LLM synthesizes a narrative answer with citations.
- `hybrid`      — both; structured filters shrink the pool, semantic ranks.

Every LLM-produced shape (the route label, the StructuredQuery) goes through
Pydantic validation BEFORE we touch the DB. Free-form SQL never reaches the
database.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core import llm
from app.models.candidate import Candidate
from app.schemas.search import SearchRequest
from app.services import search as search_service
from app.services.qa_pool_query import (
    ALLOWED_COLUMNS,
    FilterClause,
    StructuredQuery,
    execute as exec_query,
)

Route = Literal["structured", "semantic", "hybrid"]


# ----- classifier --------------------------------------------------------


_CLASSIFIER_SYSTEM = (
    "You classify recruiter questions into one of three routes:\n"
    "  - structured: counts, aggregations, exact-attribute filters "
    "(e.g. \"how many Python devs in Pune\", \"candidates added last week\")\n"
    "  - semantic: fuzzy/qualitative questions about experience or fit "
    "(e.g. \"backend engineer with fintech experience\")\n"
    "  - hybrid: a fuzzy descriptor PLUS hard filters "
    "(e.g. \"python devs in Pune who have worked on payments\")\n"
    'Respond with ONLY a JSON object: {"route": "structured" | "semantic" | "hybrid"}.'
)


def _fake_classify(question: str) -> Route:
    """Deterministic dev-mode classifier."""
    q = question.lower()
    has_count = bool(
        re.search(r"\bhow many\b|\bcount\b|\bnumber of\b|\bhow much\b", q)
    )
    has_filter_only = bool(
        re.search(
            r"\b(in|located in|added|joined|with notice|with experience|in stage)\b",
            q,
        )
    )
    has_fuzzy = bool(
        re.search(
            r"\b(similar|like|experience|fit|background|worked on|expertise)\b",
            q,
        )
    )
    if has_count and not has_fuzzy:
        return "structured"
    if has_fuzzy and (has_count or has_filter_only):
        return "hybrid"
    if has_filter_only and not has_fuzzy and not has_count:
        return "structured"
    return "semantic"


def classify(question: str) -> Route:
    if llm.qa_is_fake():
        return _fake_classify(question)
    raw = llm.qa_complete(_CLASSIFIER_SYSTEM, question, json_mode=True, temperature=0)
    parsed = json.loads(raw)
    route = parsed.get("route")
    if route not in {"structured", "semantic", "hybrid"}:
        # If the model gives nonsense, fall back to semantic — safe default.
        return "semantic"
    return route  # type: ignore[return-value]


# ----- SQL gen -----------------------------------------------------------


_SQLGEN_SYSTEM = f"""\
You translate a recruiter question into a JSON object matching this schema.
Return ONLY the JSON, no prose.

Schema:
{{
  "aggregate": "count" | "list",
  "filters": [
    {{ "column": <one of {list(ALLOWED_COLUMNS)}>,
       "op": "eq"|"neq"|"gt"|"gte"|"lt"|"lte"|"ilike"|"is_null"|"not_null"|"contains_skill"|"in",
       "value": <string|number|list|null> }}
  ],
  "select": [<column>],
  "group_by": <column or null>,
  "order_by": <column or null>,
  "desc": true|false,
  "limit": 1..500
}}

Notes:
- Use 'ilike' for partial location/title matches; the value is matched case-
  insensitively with %% wildcards added by the system.
- Use 'contains_skill' to search inside the skills array.
- For "how many" questions, set aggregate=count.
- For "list / show me" questions, aggregate=list and pick reasonable select cols.
- Do NOT invent columns.
"""


def _fake_sqlgen(question: str) -> StructuredQuery:
    """Pull obvious tokens out of the question; build a sensible query."""
    q = question.lower()

    filters: list[FilterClause] = []
    # exp >= N years
    m = re.search(r"(\d+)\s*\+?\s*(?:years|yrs|year)", q)
    if m:
        filters.append(
            FilterClause(column="total_exp_years", op="gte", value=float(m.group(1)))
        )
    # location: "in <Place>"
    m = re.search(r"\bin\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)", question)
    if m:
        filters.append(
            FilterClause(column="location", op="ilike", value=m.group(1))
        )
    # skill: any common token mentioned in question
    for skill in ("python", "java", "go", "kafka", "postgres", "react", "fastapi"):
        if skill in q:
            filters.append(
                FilterClause(column="skills", op="contains_skill", value=skill)
            )

    aggregate: Literal["count", "list"] = (
        "count" if re.search(r"\bhow many\b|\bnumber of\b", q) else "list"
    )

    return StructuredQuery(aggregate=aggregate, filters=filters, limit=50)


def gen_query(question: str) -> StructuredQuery:
    if llm.qa_is_fake():
        return _fake_sqlgen(question)
    raw = llm.qa_complete(_SQLGEN_SYSTEM, question, json_mode=True, temperature=0)
    parsed = json.loads(raw)
    return StructuredQuery.model_validate(parsed)


# ----- synthesis ---------------------------------------------------------


def _fake_synthesize_structured(question: str, rows: list[dict]) -> str:
    if not rows:
        return "No candidates match those criteria."
    if "count" in rows[0] and len(rows) == 1 and "group_key" not in rows[0]:
        return f"There are {rows[0]['count']} candidates matching."
    if "group_key" in rows[0]:
        lines = [f"- {r['group_key']}: {r['count']}" for r in rows]
        return "Counts by group:\n" + "\n".join(lines)
    # list path
    lines = []
    for r in rows[:10]:
        name = r.get("full_name", "?")
        bits = [
            str(r[k]) for k in ("current_title", "current_company", "location")
            if r.get(k)
        ]
        lines.append(f"- {name}{' · ' + ' · '.join(bits) if bits else ''}")
    suffix = f"\n…and {len(rows) - 10} more." if len(rows) > 10 else ""
    return "Matching candidates:\n" + "\n".join(lines) + suffix


def _synthesize_structured(question: str, rows: list[dict]) -> str:
    if llm.qa_is_fake():
        return _fake_synthesize_structured(question, rows)
    return llm.qa_complete(
        system=(
            "Summarize the SQL result rows in plain English to answer the user's "
            "question. Be precise and factual; if the result is empty, say so."
        ),
        user=f"Question: {question}\n\nRows:\n{json.dumps(rows, default=str)}",
    )


SEMANTIC_LIMIT = 50  # ranked candidates returned to the UI; synthesis still uses top 10
SYNTHESIS_TOP_K = 10


def _build_search_request(
    question: str,
    *,
    base_filters: StructuredQuery | None,
    limit: int = SEMANTIC_LIMIT,
) -> SearchRequest:
    skills: list[str] = []
    location: str | None = None
    exp_min: float | None = None
    exp_max: float | None = None
    if base_filters is not None:
        for f in base_filters.filters:
            if f.column == "skills" and f.op == "contains_skill":
                skills.append(str(f.value))
            elif f.column == "location" and f.op in {"ilike", "eq"}:
                location = str(f.value)
            elif f.column == "total_exp_years" and f.op in {"gte", "gt"}:
                exp_min = float(f.value)
            elif f.column == "total_exp_years" and f.op in {"lte", "lt"}:
                exp_max = float(f.value)
    return SearchRequest(
        q=question,
        location=location,
        skills=skills,
        exp_min=exp_min,
        exp_max=exp_max,
        limit=limit,
    )


def _semantic_pick(
    db: Session,
    question: str,
    *,
    base_filters: StructuredQuery | None,
    limit: int = SEMANTIC_LIMIT,
    visible_ids: Select | None = None,
) -> tuple[list[tuple[Candidate, float | None]], int]:
    """Returns (hits, pool_size). `hits` is (candidate, score) ordered
    best-first. `pool_size` is the total number of candidates the semantic
    ranker considered (i.e. those matching base_filters AND with embeddings),
    used downstream to compute a true percentile rank.

    `visible_ids` (when set) further constrains the pool to those candidate
    ids — used to scope client-role users to their own pool."""
    req = _build_search_request(
        question, base_filters=base_filters, limit=limit
    )
    hits = search_service.search(db, req, visible_ids=visible_ids)
    pool_size = search_service.count(db, req, visible_ids=visible_ids)
    return hits, pool_size


def _percentile(rank: int, pool_size: int) -> float:
    """Match percentile, 0–100. 100 means best in the pool; the worst
    candidate in a pool of N gets `1/N * 100` (never zero, so a single match
    in a pool of one reads as 100%)."""
    if pool_size <= 0:
        return 100.0
    return round((pool_size - rank + 1) / pool_size * 100, 1)


def _fake_synthesize_semantic(
    question: str, hits: list[tuple[Candidate, float | None]]
) -> str:
    if not hits:
        return "No candidates match the description."
    lines = []
    for c, _score in hits[:SYNTHESIS_TOP_K]:
        bits = [
            x for x in (c.current_title, c.current_company, c.location) if x
        ]
        lines.append(f"- {c.full_name}{' · ' + ' · '.join(bits) if bits else ''}")
    return "Top matches:\n" + "\n".join(lines)


def _synthesize_semantic(
    question: str, hits: list[tuple[Candidate, float | None]]
) -> str:
    if llm.qa_is_fake():
        return _fake_synthesize_semantic(question, hits)
    profiles = [
        {
            "id": c.id,
            "full_name": c.full_name,
            "current_title": c.current_title,
            "current_company": c.current_company,
            "location": c.location,
            "skills": c.skills,
            "summary": (c.summary or "")[:300],
        }
        for c, _score in hits[:SYNTHESIS_TOP_K]
    ]
    return llm.qa_complete(
        system=(
            "Answer the recruiter's question using the candidate profiles below. "
            "Cite each candidate by name when you mention them. Be brief."
        ),
        user=f"Question: {question}\n\nCandidates:\n{json.dumps(profiles)}",
    )


# ----- public api --------------------------------------------------------


def answer_pool(
    db: Session,
    question: str,
    *,
    visible_ids: Select | None = None,
) -> dict:
    route = classify(question)

    if route == "structured":
        q = gen_query(question)
        rows = exec_query(db, q, visible_ids=visible_ids)
        return {
            "route": route,
            "answer": _synthesize_structured(question, rows),
            "citations": [],
            "rows": rows,
            "matched_count": len(rows),
        }

    if route == "semantic":
        hits, pool_size = _semantic_pick(
            db, question, base_filters=None, visible_ids=visible_ids
        )
        return {
            "route": route,
            "answer": _synthesize_semantic(question, hits),
            "citations": [
                {
                    "type": "row",
                    "id": c.id,
                    "snippet": c.full_name,
                    "score": score,
                    "percentile": _percentile(i + 1, pool_size),
                }
                for i, (c, score) in enumerate(hits)
            ],
            "rows": None,
            "matched_count": len(hits),
        }

    # hybrid
    q = gen_query(question)
    hits, pool_size = _semantic_pick(
        db, question, base_filters=q, visible_ids=visible_ids
    )
    return {
        "route": route,
        "answer": _synthesize_semantic(question, hits),
        "citations": [
            {
                "type": "row",
                "id": c.id,
                "snippet": c.full_name,
                "score": score,
                "percentile": _percentile(i + 1, pool_size),
            }
            for i, (c, score) in enumerate(hits)
        ],
        "rows": None,
        "matched_count": len(hits),
    }
