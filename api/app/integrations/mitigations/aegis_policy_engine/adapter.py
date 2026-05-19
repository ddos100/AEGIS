"""AEGIS Policy Engine internal mitigation adapters (Phase 7.5+).

These are AEGIS-native governance actions that don't touch any external
vendor API.  They enforce internal workflow gates:

  require_aisia_completion — blocks an AI system from moving past
      "approved" status until its AISIA assessment is completed and
      signed off by the designated approver.

  require_risk_recompute — forces an immediate risk-score recalculation
      for the affected AI system before the mitigation can proceed to
      the next lifecycle step.

Both modify AEGIS DB state only.  Dry-run at v1 so the operator sees
the proposed gate before it takes effect.
"""
from __future__ import annotations

from app.integrations.mitigations._drylib import dry_apply, dry_rollback, dry_verify
from app.integrations.mitigations.base import BaseMitigationAdapter, register

_API_LABEL = "AEGIS internal policy engine"


@register(integration="aegis_policy_engine", action="require_aisia_completion")
class RequireAISIACompletion(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="POL-AISIA",
            required=["ai_system_id"],
            params=params,
            detail_tmpl="would gate AI system {ai_system_id!r} — status cannot "
                        "advance past 'approved' until AISIA assessment is completed "
                        "and signed off by the designated approver",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)


@register(integration="aegis_policy_engine", action="require_risk_recompute")
class RequireRiskRecompute(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="POL-RISK",
            required=["ai_system_id"],
            params=params,
            detail_tmpl="would force immediate risk-score recalculation for AI "
                        "system {ai_system_id!r} before mitigation can advance "
                        "to the next lifecycle step",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)
