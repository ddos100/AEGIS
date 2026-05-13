"""Completeness scoring — Python mirror of the plpgsql function.

Kept here so the API layer can compute and preview a score without a DB
round-trip (e.g. while rendering the edit form). The DB-side function in
migration 002 remains the source of truth and is what gets persisted to
``ai_systems.completeness_score`` via the BEFORE INSERT/UPDATE trigger.

If you change one, change the other.
"""
from __future__ import annotations

from typing import Mapping

# (field name, weight, predicate) tuples — same order/values as the plpgsql.
_FIELD_WEIGHTS: list[tuple[str, int]] = [
    ("intended_purpose",       15),
    ("owner_user_id",          10),
    ("department_id",          10),
    ("data_types_processed",   10),
    ("affected_data_subjects", 10),
    ("deployment_type",         5),
    ("first_deployed_at",       5),
    ("human_oversight_desc",   10),
    ("output_type",             5),
    ("eu_ai_act_category",      5),
    ("geographic_scope",        5),
    ("user_population",         5),
    # aisia_status counts only if not 'not_started'
    ("__aisia_started",         5),
]


def _is_populated(field: str, value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return len(value) > 0
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def compute_completeness(system: Mapping[str, object]) -> int:
    """Return a 0-100 completeness score for the given system dict.

    Accepts either a Pydantic model dump or a raw dict with the same keys
    as :class:`app.models.ai_system.AISystem`.
    """
    score = 0
    for field, weight in _FIELD_WEIGHTS:
        if field == "__aisia_started":
            if system.get("aisia_status") not in (None, "", "not_started"):
                score += weight
            continue
        if _is_populated(field, system.get(field)):
            score += weight
    return min(score, 100)
