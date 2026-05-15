"""Eramba GRC integration endpoint.

  POST /v1/integrations/eramba/sync   Push the AEGIS Registry into Eramba

The credentials come from an IntegrationCredential row (integration='eramba')
created via the standard Phase 3 /v1/integrations flow.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.core.crypto import decrypt_credentials
from app.core.deps import CurrentUser, DBSession, require_admin
from app.integrations.eramba.client import push_systems
from app.models.integration_credential import IntegrationCredential

router = APIRouter(prefix="/integrations/eramba", tags=["integrations"])


@router.post("/sync")
async def sync_eramba(
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],
    integration_id: UUID | None = None,
):
    """Trigger an Eramba push. If integration_id is omitted, uses the first
    active eramba credential row for the tenant."""
    stmt = select(IntegrationCredential).where(IntegrationCredential.integration == "eramba")
    if integration_id:
        stmt = stmt.where(IntegrationCredential.id == integration_id)
    cred = (await db.execute(stmt)).scalar_one_or_none()
    if cred is None:
        raise HTTPException(status_code=404, detail="No Eramba credential configured. "
                                                    "Add one in /integrations first.")
    try:
        creds = decrypt_credentials(cred.credentials_ciphertext)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500,
                            detail=f"Failed to decrypt credentials: {exc}") from exc

    result = await push_systems(credentials=creds, tenant_id=user.tenant_id, session=db)
    return result
