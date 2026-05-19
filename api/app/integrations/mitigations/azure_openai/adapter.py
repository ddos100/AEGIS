"""Azure OpenAI mitigation adapters (Phase 7.5+).

Real-mode uses Azure OpenAI Management API:

  PUT /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices/
      accounts/{acct}/contentFilters/{filterName}
  PATCH /subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices/
        accounts/{acct}/deployments/{deployment}

Enables Azure AI Content Safety filters on Azure OpenAI deployments
to enforce responsible AI guardrails.
Service principal w/ Cognitive Services Contributor.  Dry-run at v1.
"""
from __future__ import annotations

from app.integrations.mitigations._drylib import dry_apply, dry_rollback, dry_verify
from app.integrations.mitigations.base import BaseMitigationAdapter, register

_API_LABEL = "Azure OpenAI Content Safety filters"


@register(integration="azure_openai", action="enable_content_safety")
class AzureOpenAIEnableContentSafety(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="AOAI-CS",
            required=["deployment_name", "filter_severity"],
            params=params,
            detail_tmpl="would enable Content Safety filter at severity "
                        "{filter_severity!r} on Azure OpenAI deployment "
                        "{deployment_name!r}",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)
