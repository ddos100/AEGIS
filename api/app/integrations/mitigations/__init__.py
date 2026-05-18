"""Mitigation push adapters (Phase 7.5).

Each vendor adapter implements `BaseMitigationAdapter` and registers
itself via `@register("vendor", "action")`. The mitigation pipeline
looks up `(integration, action)` from a `mitigation_actions` row and
dispatches to the matching adapter.

Phase 7.5 design contract
-------------------------
1. **Propose-only is still the default.** Even when an adapter is
   registered + creds are configured, the row is only pushed when the
   operator explicitly POSTs to `/v1/mitigations/{id}/push`. There is
   no autonomous queue-drain in v1.
2. **Dry-run by default.** Every adapter ships with `dry_run = True`.
   In dry-run mode `apply()` records the intended change to the DB
   audit log and reports success without hitting the vendor API.
   Flipping `dry_run = False` is a per-deployment customisation done
   by SCLLP during customer onboarding.
3. **Determinism + privacy.** Adapters carry no PII; they receive only
   the threat-mitigation step's `params` (categories, domains, app IDs,
   policy refs) plus the tenant's already-Fernet-encrypted integration
   credentials. Vendor responses are summarised to a short
   `vendor_ref` string — the full body is never persisted.
"""
from app.integrations.mitigations.base import (
    BaseMitigationAdapter,
    MitigationApplyResult,
    MitigationVerifyResult,
    get_adapter,
    list_adapters,
    register,
    load_all_adapters,
)
from app.integrations.mitigations import zscaler  # noqa: F401  registration side-effect
from app.integrations.mitigations import cisco_umbrella  # noqa: F401
from app.integrations.mitigations import cloudflare_gateway  # noqa: F401

__all__ = [
    "BaseMitigationAdapter", "MitigationApplyResult", "MitigationVerifyResult",
    "get_adapter", "list_adapters", "register", "load_all_adapters",
]
