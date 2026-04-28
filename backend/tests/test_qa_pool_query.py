"""StructuredQuery: the safety boundary for pool-Q&A SQL.

These tests prove that columns/operators outside the whitelist are rejected
at the Pydantic layer, BEFORE any SQL is built. So a malicious or
hallucinated LLM output simply can't reach the DB.
"""

import pytest
from pydantic import ValidationError

from app.services.qa_pool_query import (
    ALLOWED_COLUMNS,
    FilterClause,
    StructuredQuery,
    query_to_sql,
)


def test_unknown_column_rejected():
    with pytest.raises(ValidationError):
        FilterClause(column="DROP TABLE", op="eq", value=1)


def test_unknown_op_rejected():
    with pytest.raises(ValidationError):
        FilterClause(column="location", op="LIKE; --", value="Pune")  # type: ignore


def test_count_all():
    q = StructuredQuery(aggregate="count")
    sql, params = query_to_sql(q)
    assert sql == "SELECT COUNT(*) AS count FROM v_candidate_search"
    assert params == {}


def test_count_with_filters():
    q = StructuredQuery(
        aggregate="count",
        filters=[
            FilterClause(column="location", op="ilike", value="Pune"),
            FilterClause(column="total_exp_years", op="gte", value=5),
        ],
    )
    sql, params = query_to_sql(q)
    assert "WHERE location ILIKE :p0 AND total_exp_years >= :p1" in sql
    assert params == {"p0": "%Pune%", "p1": 5}


def test_count_grouped():
    q = StructuredQuery(aggregate="count", group_by="current_stage_name")
    sql, params = query_to_sql(q)
    assert "GROUP BY current_stage_name" in sql
    assert "ORDER BY count DESC" in sql


def test_list_with_select_and_order():
    q = StructuredQuery(
        aggregate="list",
        select=["full_name", "location", "total_exp_years"],
        order_by="total_exp_years",
        desc=True,
        limit=20,
    )
    sql, params = query_to_sql(q)
    assert "SELECT full_name, location, total_exp_years FROM v_candidate_search" in sql
    assert "ORDER BY total_exp_years DESC" in sql
    assert "LIMIT 20" in sql


def test_contains_skill_uses_lower_cast():
    q = StructuredQuery(
        aggregate="count",
        filters=[FilterClause(column="skills", op="contains_skill", value="Kafka")],
    )
    sql, params = query_to_sql(q)
    assert "LOWER(CAST(skills AS TEXT)) LIKE :p0" in sql
    assert params == {"p0": "%kafka%"}


def test_in_filter_expands_params():
    q = StructuredQuery(
        aggregate="list",
        filters=[
            FilterClause(
                column="current_stage_name",
                op="in",
                value=["Interested", "Submitted"],
            )
        ],
    )
    sql, params = query_to_sql(q)
    assert "current_stage_name IN (:p0_0, :p0_1)" in sql
    assert params == {"p0_0": "Interested", "p0_1": "Submitted"}


def test_is_null_filter_no_param():
    q = StructuredQuery(
        aggregate="count",
        filters=[FilterClause(column="email", op="is_null")],
    )
    sql, params = query_to_sql(q)
    assert "email IS NULL" in sql
    assert params == {}


def test_op_requires_value_when_relevant():
    with pytest.raises(ValidationError):
        FilterClause(column="location", op="ilike")  # missing value


def test_in_op_requires_list_value():
    with pytest.raises(ValidationError):
        FilterClause(column="location", op="in", value="Pune")  # not a list


def test_limit_clamped():
    with pytest.raises(ValidationError):
        StructuredQuery(limit=10000)


def test_allowed_columns_match_whitelist():
    """If we forgot to update one side, this test catches it."""
    # Sample a few from the whitelist and verify they're accepted.
    for col in ("location", "skills", "current_stage_name", "note_count"):
        assert col in ALLOWED_COLUMNS
        FilterClause(column=col, op="not_null")  # constructs cleanly
