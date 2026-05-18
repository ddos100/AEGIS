"""Cisco Umbrella mitigation adapter (Phase 7.5).

Implements the `domain_destination_list` and `domain_destination_list_by_country`
primitives. Real-mode operations call:

  POST {UMBRELLA}/policies/v2/destinationlists                — create list
  PATCH {UMBRELLA}/policies/v2/destinationlists/{id}/destinations
  POST {UMBRELLA}/policies/v2/policies/{id}/destinationlists  — attach
"""
from __future__ import annotations

import hashlib
from typing import Any

from app.integrations.mitigations.base import (
    BaseMitigationAdapter,
    MitigationApplyResult,
    MitigationVerifyResult,
    register,
)


def _list_ref(name: str) -> str:
    return f"UMBR-DL-{hashlib.sha256(name.encode()).hexdigest()[:8]}"


@register(integration="cisco_umbrella", action="domain_destination_list")
class UmbrellaDestinationListAdapter(BaseMitigationAdapter):
    integration = "cisco_umbrella"
    action = "domain_destination_list"
    dry_run = True

    async def apply(self, *, credentials, params):
        ref = (params or {}).get("list_ref") or "AEGIS-AUTO"
        return MitigationApplyResult(
            ok=True, dry_run=True, vendor_ref=_list_ref(ref),
            detail=f"DRY-RUN: would push destination list {ref!r} to Cisco Umbrella "
                    "and attach to default policy",
            state_blob={"list_ref": ref},
        )

    async def verify(self, *, credentials, params, state_blob):
        ref = (state_blob or {}).get("list_ref", "?")
        return MitigationVerifyResult(
            verified=True, dry_run=True,
            detail=f"DRY-RUN: would GET destinationlists and confirm "
                    f"{ref!r} attached to active policy",
        )

    async def rollback(self, *, credentials, params, state_blob):
        ref = (state_blob or {}).get("list_ref", "?")
        return MitigationApplyResult(
            ok=True, dry_run=True, vendor_ref=_list_ref(ref),
            detail=f"DRY-RUN: would detach {ref!r} from active policy "
                    f"(list retained for replay)",
        )


@register(integration="cisco_umbrella", action="domain_destination_list_by_country")
class UmbrellaDestinationListByCountryAdapter(UmbrellaDestinationListAdapter):
    integration = "cisco_umbrella"
    action = "domain_destination_list_by_country"
