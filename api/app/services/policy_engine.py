"""Priority-ordered policy rule evaluator.

Rules live in the ``policies`` table — tenant-scoped. Each row has a
``conditions`` JSONB blob and an ``action`` string. Evaluation:

  1. Load active policies in ascending priority order.
  2. For each policy, all condition keys must match (AND semantics).
  3. First matching policy wins. Default if no match: ``allow``.
  4. If the chosen action is anything other than ``allow``, a row is appended
     to ``policy_violations``.

Condition keys (all optional, every key tightens the rule):

  ai_category          list[str]   match system.category
  risk_level           list[str]   one of: critical | high | medium | low
  data_classification  list[str]   any of system.data_types_processed
  user_group           list[str]   any of user.groups (when the call is user-scoped)
  department_id        list[uuid]  exact match
  provider_country     list[str]   exact match on catalogue provider.hq_country
  is_shadow            bool        system.is_shadow == value
  eu_ai_act_category   list[str]
  policy_status        list[str]   system.policy_status (for transitive rules)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.models.ai_system import AISystem
from app.models.policy import Policy
from app.models.policy_violation import PolicyViolation

ALLOW   = "allow"
MONITOR = "monitor"
ALERT   = "alert"
BLOCK   = "block"
REQUIRE_APPROVAL = "require_approval"

VALID_ACTIONS = {ALLOW, MONITOR, ALERT, BLOCK, REQUIRE_APPROVAL}


@dataclass(slots=True)
class PolicyDecision:
    action: str
    policy_id: UUID | None = None
    policy_name: str | None = None
    matched_conditions: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


def evaluate_conditions(conditions: dict[str, Any], *,
                        system: AISystem,
                        user_groups: list[str] | None = None) -> tuple[bool, list[str]]:
    """Return (matched, matched_condition_keys). All conditions must match."""
    matched: list[str] = []

    def _intersects(target_list, condition_value):
        cv = [v.lower() if isinstance(v, str) else v for v in condition_value]
        tl = [t.lower() if isinstance(t, str) else t for t in (target_list or [])]
        return any(t in cv for t in tl)

    def _equals(value, expected):
        if isinstance(expected, list):
            return value in expected
        return value == expected

    # ai_category
    if "ai_category" in conditions:
        if not _equals(system.category, conditions["ai_category"]):
            return False, matched
        matched.append("ai_category")

    if "risk_level" in conditions:
        if not _equals(system.risk_level, conditions["risk_level"]):
            return False, matched
        matched.append("risk_level")

    if "data_classification" in conditions:
        if not _intersects(system.data_types_processed, conditions["data_classification"]):
            return False, matched
        matched.append("data_classification")

    if "is_shadow" in conditions:
        if bool(system.is_shadow) != bool(conditions["is_shadow"]):
            return False, matched
        matched.append("is_shadow")

    if "eu_ai_act_category" in conditions:
        if not _equals(system.eu_ai_act_category, conditions["eu_ai_act_category"]):
            return False, matched
        matched.append("eu_ai_act_category")

    if "policy_status" in conditions:
        if not _equals(system.policy_status, conditions["policy_status"]):
            return False, matched
        matched.append("policy_status")

    if "department_id" in conditions:
        if not _equals(str(system.department_id) if system.department_id else None,
                       [str(x) for x in conditions["department_id"]]):
            return False, matched
        matched.append("department_id")

    if "user_group" in conditions:
        if not user_groups:
            return False, matched
        if not _intersects(user_groups, conditions["user_group"]):
            return False, matched
        matched.append("user_group")

    return True, matched


async def evaluate(
    *,
    session,
    system: AISystem,
    user_groups: list[str] | None = None,
    vector: str | None = None,
    event_context: dict[str, Any] | None = None,
) -> PolicyDecision:
    """Run the full policy evaluation. Caller supplies an open DB session
    bound to the correct tenant context."""
    stmt = (
        select(Policy)
        .where(Policy.is_active.is_(True))
        .order_by(Policy.priority.asc())
    )
    policies = (await session.execute(stmt)).scalars().all()

    for policy in policies:
        ok, matched = evaluate_conditions(
            policy.conditions or {}, system=system, user_groups=user_groups,
        )
        if not ok:
            continue
        decision = PolicyDecision(
            action=policy.action,
            policy_id=policy.id,
            policy_name=policy.name,
            matched_conditions=matched,
            config=policy.action_config or {},
        )
        if policy.action != ALLOW:
            await _log_violation(session, decision, system, vector, event_context)
        return decision

    return PolicyDecision(action=ALLOW, matched_conditions=[])


async def _log_violation(session, decision: PolicyDecision, system: AISystem,
                         vector: str | None, event_context: dict[str, Any] | None) -> None:
    violation = PolicyViolation(
        tenant_id=system.tenant_id,
        policy_id=decision.policy_id,
        ai_system_id=system.id,
        vector=vector,
        action_taken=decision.action,
        violation_context={
            "matched_conditions": decision.matched_conditions,
            "policy_config":      decision.config,
            "event":              event_context or {},
        },
    )
    session.add(violation)
