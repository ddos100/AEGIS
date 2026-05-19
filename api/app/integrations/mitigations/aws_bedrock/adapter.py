"""AWS Bedrock mitigation adapters (Phase 7.5+).

Real-mode uses AWS Bedrock APIs:

  bedrock:CreateGuardrail / bedrock:UpdateGuardrail
  bedrock:CreateProvisionedModelThroughput (with maxModelUnits cap)
  bedrock:TagResource (cost allocation tags for tracking)

Attaches guardrails to Bedrock model invocations and caps provisioned
throughput to prevent runaway AI spend.
AssumeRole w/ bedrock:*Guardrail + bedrock:*ProvisionedModelThroughput.
Dry-run at v1.
"""
from __future__ import annotations

from app.integrations.mitigations._drylib import dry_apply, dry_rollback, dry_verify
from app.integrations.mitigations.base import BaseMitigationAdapter, register

_API_LABEL = "AWS Bedrock guardrails + provisioned throughput"


@register(integration="aws_bedrock", action="attach_guardrail")
class BedrockAttachGuardrail(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="BDR-GR",
            required=["guardrail_name", "model_id"],
            params=params,
            detail_tmpl="would create/update Bedrock guardrail {guardrail_name!r} "
                        "and attach it to model {model_id!r} with content + topic filters",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)


@register(integration="aws_bedrock", action="provisioned_throughput_cap")
class BedrockProvisionedThroughputCap(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="BDR-CAP",
            required=["model_id", "max_model_units"],
            params=params,
            detail_tmpl="would cap Bedrock provisioned throughput for {model_id!r} "
                        "at {max_model_units} model units to limit AI spend",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)
