"""Palo Alto Panorama mitigation adapter (Phase 7.5+).

Real-mode operations target Panorama via the XML or REST API:

  POST /restapi/v10.2/Objects/CustomURLCategories  — create category
  POST /restapi/v10.2/Policies/SecurityRules       — attach to rule
  POST /restapi/v10.2/api/?type=commit             — commit candidate

Service-account auth via API key. Real-mode is intentionally NOT
enabled in v1 — `dry_run = True` is the locked default per
PHASE-7-PLAN.md §3.
"""
from __future__ import annotations

from app.integrations.mitigations._drylib import (
    dry_apply,
    dry_rollback,
    dry_verify,
)
from app.integrations.mitigations.base import (
    BaseMitigationAdapter,
    MitigationApplyResult,
    MitigationVerifyResult,
    register,
)

_API_LABEL = "Panorama custom URL categories + commit"


@register(integration="palo_alto", action="block_url_category")
class PaloAltoBlockUrlCategory(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="PAN-CAT", required=["category"], params=params,
            detail_tmpl="would create/update Panorama custom URL category "
                         "{category!r} and commit candidate config",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)


@register(integration="palo_alto", action="block_url_category_by_provider_country")
class PaloAltoBlockUrlByCountry(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="PAN-CAT-CC", required=["country_denylist"], params=params,
            detail_tmpl="would push Panorama category blocking provider "
                         "countries: {country_denylist}",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)


@register(integration="palo_alto", action="block_url_category_by_data_class")
class PaloAltoBlockUrlByDataClass(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="PAN-CAT-DC", required=["category"], params=params,
            detail_tmpl="would push Panorama category {category!r} scoped to "
                         "data classes {data_classes}",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)


@register(integration="palo_alto", action="block_url_category_for_department")
class PaloAltoBlockUrlForDept(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="PAN-CAT-DEPT", required=["category"], params=params,
            detail_tmpl="would push Panorama category {category!r} restricted "
                         "to departments {departments}",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)
