"""Pool Q&A's structured (SQL) path.

The LLM returns a `StructuredQuery` Pydantic object — never raw SQL. This
module translates that into a parameterized SQL query against the read-only
`v_candidate_search` view.

The whitelist `ALLOWED_COLUMNS` is the safety boundary. Columns or operators
not in the whitelist are rejected by Pydantic before they ever touch the DB,
so a malicious or hallucinated query simply can't be executed.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

# All columns exposed by v_candidate_search. Lockstep with the migration.
ALLOWED_COLUMNS: tuple[str, ...] = (
    "candidate_id",
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
    "created_at",
    "current_stage_name",
    "current_job_title",
    "active_link_count",
    "resume_count",
    "note_count",
)

# Operators the LLM may use, mapped to literal SQL fragments. Each takes one
# bound parameter (or none, for is_null/not_null).
_NUMERIC_OPS = {
    "eq": "=",
    "neq": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
}
_STRING_OPS = {"ilike": "ILIKE", "eq": "=", "neq": "!="}


class FilterClause(BaseModel):
    column: Literal[ALLOWED_COLUMNS] = Field(...)  # type: ignore[valid-type]
    op: Literal[
        "eq", "neq", "gt", "gte", "lt", "lte",
        "ilike", "is_null", "not_null", "contains_skill", "in",
    ]
    value: Any = None

    @model_validator(mode="after")
    def _check_value_present(self):
        if self.op in {"is_null", "not_null"}:
            return self
        if self.value is None:
            raise ValueError(f"op {self.op!r} requires a value")
        if self.op == "in" and not isinstance(self.value, list):
            raise ValueError("op 'in' requires a list value")
        return self


class StructuredQuery(BaseModel):
    """The LLM emits this. It does NOT emit SQL.

    `aggregate=count` returns one row with `{count, ...group cols}`.
    `aggregate=list` returns up to `limit` candidate rows with the requested
    `select` columns (defaults to all).
    """

    aggregate: Literal["count", "list"] = "list"
    filters: list[FilterClause] = []
    select: list[Literal[ALLOWED_COLUMNS]] = []  # type: ignore[valid-type]
    group_by: Literal[ALLOWED_COLUMNS] | None = None  # type: ignore[valid-type]
    order_by: Literal[ALLOWED_COLUMNS] | None = None  # type: ignore[valid-type]
    desc: bool = False
    limit: int = Field(default=50, ge=1, le=500)


def _filter_to_sql(idx: int, f: FilterClause) -> tuple[str, dict[str, Any]]:
    """Render one FilterClause into a SQL fragment + bind params.

    Each call returns its own parameter name (`p0`, `p1`, ...) so we can stack
    multiple AND-combined clauses without colliding.
    """
    pname = f"p{idx}"
    col = f.column

    if f.op in _NUMERIC_OPS:
        return f"{col} {_NUMERIC_OPS[f.op]} :{pname}", {pname: f.value}
    if f.op == "ilike":
        return f"{col} ILIKE :{pname}", {pname: f"%{f.value}%"}
    if f.op == "is_null":
        return f"{col} IS NULL", {}
    if f.op == "not_null":
        return f"{col} IS NOT NULL", {}
    if f.op == "contains_skill":
        # The view exposes `skills` as JSON. We compare on the lowercased text
        # representation — works on both Postgres (jsonb) and SQLite.
        return (
            f"LOWER(CAST({col} AS TEXT)) LIKE :{pname}",
            {pname: f"%{str(f.value).lower()}%"},
        )
    if f.op == "in":
        # Render as expanded params: in (:p0_0, :p0_1, ...)
        items = list(f.value)  # type: ignore[arg-type]
        names = [f"{pname}_{i}" for i in range(len(items))]
        params = {n: v for n, v in zip(names, items)}
        return f"{col} IN ({', '.join(':' + n for n in names)})", params
    raise ValueError(f"unsupported op {f.op!r}")


def query_to_sql(q: StructuredQuery) -> tuple[str, dict[str, Any]]:
    """Compile a StructuredQuery into a SQL string + bound params.

    Returns SQL that can be passed straight to `session.execute(text(sql), params)`.
    """
    where_parts: list[str] = []
    params: dict[str, Any] = {}
    for i, f in enumerate(q.filters):
        frag, p = _filter_to_sql(i, f)
        where_parts.append(frag)
        params.update(p)
    where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""

    if q.aggregate == "count":
        if q.group_by:
            sql = (
                f"SELECT {q.group_by} AS group_key, COUNT(*) AS count "
                f"FROM v_candidate_search{where_sql} "
                f"GROUP BY {q.group_by} ORDER BY count DESC LIMIT {q.limit}"
            )
        else:
            sql = f"SELECT COUNT(*) AS count FROM v_candidate_search{where_sql}"
        return sql, params

    # aggregate == list
    cols = ", ".join(q.select) if q.select else "*"
    order_sql = ""
    if q.order_by:
        order_sql = f" ORDER BY {q.order_by} {'DESC' if q.desc else 'ASC'}"
    sql = (
        f"SELECT {cols} FROM v_candidate_search"
        f"{where_sql}{order_sql} LIMIT {q.limit}"
    )
    return sql, params


def execute(db: Session, q: StructuredQuery) -> list[dict[str, Any]]:
    """Run the structured query against v_candidate_search and return rows
    as plain dicts. Postgres-only — the view doesn't exist on SQLite."""
    sql, params = query_to_sql(q)
    result = db.execute(text(sql), params)
    rows = result.mappings().all()
    return [dict(r) for r in rows]
