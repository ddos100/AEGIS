"""Base class + registry for mitigation push adapters."""
from __future__ import annotations

import abc
import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass(slots=True)
class MitigationApplyResult:
    """What an adapter reports back after attempting an apply()."""
    ok: bool
    dry_run: bool
    vendor_ref: str | None = None          # opaque short reference for audit
    detail: str = ""
    error: str | None = None
    # Anything the adapter wants persisted on the mitigation_action row
    # so a later verify()/rollback() can locate the change. Must not
    # contain PII or credential material — short opaque identifiers only.
    state_blob: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MitigationVerifyResult:
    """Outcome of a verify() pass."""
    verified: bool                         # True  = still in place
    drifted:  bool = False                 # True  = present but mutated upstream
    missing:  bool = False                 # True  = upstream rule disappeared
    dry_run:  bool = True
    detail:   str = ""
    error:    str | None = None


class BaseMitigationAdapter(abc.ABC):
    """Implement one (integration, action) pair.

    Subclasses declare class attrs:

        integration   matches mitigation_actions.integration
        action        matches mitigation_actions.action
        dry_run       True  → apply()/rollback() do not call the vendor
                              and instead return a success result with
                              the intended change summarised. The wiring,
                              DB transitions, and audit_log row are all
                              still real.
                      False → adapter MUST implement the vendor calls.
    """
    integration: ClassVar[str]
    action:      ClassVar[str]
    dry_run:     ClassVar[bool] = True

    @abc.abstractmethod
    async def apply(self, *, credentials: dict[str, Any] | None,
                    params: dict[str, Any]) -> MitigationApplyResult:
        """Push the change to the vendor. Idempotent."""

    @abc.abstractmethod
    async def verify(self, *, credentials: dict[str, Any] | None,
                     params: dict[str, Any],
                     state_blob: dict[str, Any] | None) -> MitigationVerifyResult:
        """Check that the change is still in place."""

    async def rollback(self, *, credentials: dict[str, Any] | None,
                       params: dict[str, Any],
                       state_blob: dict[str, Any] | None) -> MitigationApplyResult:
        """Remove the change. Default implementation = log-only no-op so
        adapters that have no rollback path still satisfy the interface."""
        return MitigationApplyResult(
            ok=True, dry_run=self.dry_run,
            detail=f"{self.integration}.{self.action}: rollback no-op (override "
                    "BaseMitigationAdapter.rollback to implement)",
        )


# ----------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------

_ADAPTERS: dict[tuple[str, str], type["BaseMitigationAdapter"]] = {}


def register(integration: str, action: str):
    def _decorator(cls: type["BaseMitigationAdapter"]) -> type["BaseMitigationAdapter"]:
        cls.integration = integration
        cls.action = action
        key = (integration, action)
        if key in _ADAPTERS:
            raise RuntimeError(f"Duplicate adapter for {key!r}")
        _ADAPTERS[key] = cls
        return cls
    return _decorator


def get_adapter(integration: str, action: str) -> BaseMitigationAdapter:
    cls = _ADAPTERS.get((integration, action))
    if cls is None:
        raise KeyError(
            f"No adapter registered for integration={integration!r} action={action!r}. "
            f"Available: {sorted(_ADAPTERS)}"
        )
    return cls()


def list_adapters() -> list[dict[str, Any]]:
    return [
        {"integration": i, "action": a, "class": cls.__name__, "dry_run": cls.dry_run}
        for (i, a), cls in sorted(_ADAPTERS.items())
    ]


def load_all_adapters() -> None:
    """Import every vendor submodule so the @register decorators fire.

    Called at API + worker startup. Safe to call multiple times — the
    decorator raises on duplicate registration but the importlib cache
    prevents a real second-import.
    """
    import app.integrations.mitigations as pkg
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.ispkg:
            try:
                importlib.import_module(f"app.integrations.mitigations.{mod.name}.adapter")
            except ModuleNotFoundError:
                continue
