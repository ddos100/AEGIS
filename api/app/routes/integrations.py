"""Integration management endpoints (Phase 3).

  GET    /v1/integrations                   List configured credentials
  POST   /v1/integrations                   Create (admin) — accepts cleartext, stores Fernet
  GET    /v1/integrations/types             Inventory of available connectors
  GET    /v1/integrations/{id}              Detail
  PATCH  /v1/integrations/{id}              Partial update (admin)
  DELETE /v1/integrations/{id}              Remove (admin)
  POST   /v1/integrations/{id}/test         Connectivity probe (admin/analyst)
  POST   /v1/integrations/{id}/sync         Trigger sync now (admin/analyst)

Credentials are stored Fernet-encrypted and **never returned** in any response.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.crypto import decrypt_credentials, encrypt_credentials
from app.core.deps import CurrentUser, DBSession, require_admin, require_analyst
from app.integrations.connectors import (
    get_connector,
    list_connectors as registry_inventory,
)
from app.models.integration_credential import IntegrationCredential
from app.schemas.integrations import (
    ConnectorInfo,
    IntegrationBrief,
    IntegrationCreate,
    IntegrationUpdate,
    SyncRunResponse,
)

router = APIRouter(prefix="/integrations", tags=["integrations"])


# ---------- list / types / detail ----------

@router.get("", response_model=list[IntegrationBrief])
async def list_integrations(db: DBSession, user: CurrentUser):  # noqa: ARG001
    rows = (await db.execute(
        select(IntegrationCredential).order_by(IntegrationCredential.created_at)
    )).scalars().all()
    return [IntegrationBrief.model_validate(r) for r in rows]


@router.get("/types", response_model=list[ConnectorInfo])
async def list_types(user: CurrentUser):  # noqa: ARG001
    """Inventory of every registered connector — feeds the 'Add integration' wizard."""
    return [
        ConnectorInfo(integration=integ, kind=meta["kind"], cls=meta["class"], doc=meta["doc"])
        for integ, meta in sorted(registry_inventory().items())
    ]


@router.get("/{integration_id}", response_model=IntegrationBrief)
async def get_integration(
    integration_id: UUID,
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
) -> IntegrationBrief:
    row = (await db.execute(
        select(IntegrationCredential).where(IntegrationCredential.id == integration_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    return IntegrationBrief.model_validate(row)


# ---------- mutations ----------

@router.post("", response_model=IntegrationBrief, status_code=status.HTTP_201_CREATED)
async def create_integration(
    payload: IntegrationCreate,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],
) -> IntegrationBrief:
    try:
        cls = get_connector(payload.integration)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = IntegrationCredential(
        tenant_id=user.tenant_id,
        integration=payload.integration,
        kind=cls.kind,
        name=payload.name,
        credentials_ciphertext=encrypt_credentials(payload.credentials),
        scopes=payload.scopes,
        status="active",
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return IntegrationBrief.model_validate(row)


@router.patch("/{integration_id}", response_model=IntegrationBrief)
async def update_integration(
    integration_id: UUID,
    payload: IntegrationUpdate,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],  # noqa: ARG001
) -> IntegrationBrief:
    row = (await db.execute(
        select(IntegrationCredential).where(IntegrationCredential.id == integration_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Integration not found")

    changes = payload.model_dump(exclude_unset=True)
    if "credentials" in changes:
        row.credentials_ciphertext = encrypt_credentials(changes.pop("credentials"))
    for k, v in changes.items():
        setattr(row, k, v)
    await db.flush()
    await db.refresh(row)
    return IntegrationBrief.model_validate(row)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    integration_id: UUID,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],  # noqa: ARG001
) -> None:
    row = (await db.execute(
        select(IntegrationCredential).where(IntegrationCredential.id == integration_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    await db.delete(row)


# ---------- test + sync ----------

@router.post("/{integration_id}/test", response_model=SyncRunResponse)
async def test_integration(
    integration_id: UUID,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],  # noqa: ARG001
) -> SyncRunResponse:
    row, connector, creds = await _load(db, integration_id)
    result = await connector.test(creds)
    return SyncRunResponse(**result.__dict__)


@router.post("/{integration_id}/sync", response_model=SyncRunResponse)
async def sync_integration(
    integration_id: UUID,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],
) -> SyncRunResponse:
    row, connector, creds = await _load(db, integration_id)
    result = await connector.sync(
        creds,
        tenant_id=user.tenant_id,
        integration_id=row.id,
        session=db,
    )
    # Persist run metadata
    row.last_sync_at = datetime.now(timezone.utc)
    row.last_used_at = row.last_sync_at
    row.last_sync_result = {
        "ok":               result.ok,
        "discovered_count": result.discovered_count,
        "new_count":        result.new_count,
        "updated_count":    result.updated_count,
        "extra":            result.extra,
    }
    row.last_error = result.error
    row.status = "active" if result.ok else "error"
    return SyncRunResponse(**result.__dict__)


# ---------- helpers ----------

async def _load(db, integration_id: UUID):
    row = (await db.execute(
        select(IntegrationCredential).where(IntegrationCredential.id == integration_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    try:
        connector = get_connector(row.integration)
    except KeyError as exc:
        raise HTTPException(status_code=500, detail=f"Connector for {row.integration!r} unloaded") from exc
    try:
        creds = decrypt_credentials(row.credentials_ciphertext)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail="Failed to decrypt credentials — key rotation needed?") from exc
    return row, connector, creds
