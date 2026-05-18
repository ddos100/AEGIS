"""AEGIS Endpoint Agent endpoints (Phase 7.6).

Three personas / paths:

1. **Admin/analyst (`/v1/endpoint-agent/*`)** — gated by JWT + the
   AEGIS-EA module licence. Lists enrolled devices, generates
   enrolment codes, revokes devices, browses telemetry events.

2. **The Agent itself (`/v1/endpoint-agent/enroll` and
   `/v1/ingest/endpoint-agent`)** — auth differs by route:
     - /enroll  takes an `enrollment_code` minted by an admin (the
       agent has no other credential at this point).
     - /ingest  takes the signed agent token returned by /enroll
       via `Authorization: Bearer <token>`.

Privacy posture: ingest validates every event payload against a
deny-list of PII-shaped keys (`prompt`, `email`, `body`, `content`,
`url`, raw `path` etc.) and rejects with the offending key listed in
`rejected_reasons`. The agent is expected to send hashed/pattern fields
only — `path_pattern`, `command_line_sha256`, `process_name`, etc.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import desc, func, select

from app.core.config import settings
from app.core.database import SessionLocal, session_scope
from app.core.deps import CurrentUser, DBSession, require_admin
from app.core.ea_token import (
    mint_device_token,
    token_fingerprint,
    verify_device_token,
)
from app.core.licence import requires_module
from app.models.endpoint_agent_event import EndpointAgentEvent
from app.models.endpoint_device import EndpointDevice
from app.schemas.endpoint_agent import (
    DeviceBrief,
    DeviceListResponse,
    EABatch,
    EAEventListResponse,
    EAEventOut,
    EnrollmentCodeResponse,
    EnrollmentRequest,
    EnrollmentResponse,
    IngestReceipt,
)


# --------------------------------------------------------------------
# In-memory enrolment code cache (single-instance dev). Production
# binds this to Redis with a 15-minute TTL via existing redis client.
# Each code maps to a (tenant_id, expires_at). One-shot — consumed on
# successful enroll.
# --------------------------------------------------------------------
_ENROLLMENT_CODES: dict[str, tuple[UUID, datetime]] = {}


def _expiring_code() -> tuple[str, datetime]:
    code = secrets.token_urlsafe(24)
    expires = datetime.now(timezone.utc) + timedelta(minutes=15)
    return code, expires


# --------------------------------------------------------------------
# Admin-management router (JWT + AEGIS-EA gated)
# --------------------------------------------------------------------

admin_router = APIRouter(
    prefix="/endpoint-agent",
    tags=["endpoint-agent"],
    dependencies=[Depends(requires_module("AEGIS-EA"))],
)


@admin_router.get("/devices", response_model=DeviceListResponse)
async def list_devices(db: DBSession, user: CurrentUser):  # noqa: ARG001
    rows = (await db.execute(
        select(EndpointDevice).order_by(EndpointDevice.enrolled_at.desc())
    )).scalars().all()
    threshold = datetime.now(timezone.utc) - timedelta(minutes=5)
    healthy = sum(
        1 for r in rows
        if r.last_heartbeat_at and r.last_heartbeat_at >= threshold
    )
    return DeviceListResponse(
        items=[DeviceBrief.model_validate(r) for r in rows],
        total=len(rows),
        healthy=healthy,
    )


@admin_router.post("/enrollment-code", response_model=EnrollmentCodeResponse)
async def generate_enrollment_code(
    user: Annotated[CurrentUser, Depends(require_admin)],
) -> EnrollmentCodeResponse:
    """Admin mints a one-time code an agent can exchange for a token.
    Code is single-use; expires in 15 minutes."""
    code, expires = _expiring_code()
    _ENROLLMENT_CODES[code] = (user.tenant_id, expires)
    return EnrollmentCodeResponse(
        enrollment_code=code,
        expires_at=expires,
        ingest_url=f"{settings.keycloak_public_url.rstrip('/').replace('/keycloak', '')}/v1/ingest/endpoint-agent",
    )


@admin_router.post("/devices/{device_id}/revoke", response_model=DeviceBrief)
async def revoke_device(
    device_id: UUID,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],  # noqa: ARG001
):
    row = (await db.execute(
        select(EndpointDevice).where(EndpointDevice.id == device_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Device not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(row)
    return DeviceBrief.model_validate(row)


@admin_router.get("/events", response_model=EAEventListResponse)
async def list_events(
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
    kind: str | None = None,
    device_id: UUID | None = None,
    limit: int = 200,
):
    stmt = (
        select(EndpointAgentEvent, EndpointDevice.hostname)
        .join(EndpointDevice, EndpointAgentEvent.device_id == EndpointDevice.id)
        .order_by(desc(EndpointAgentEvent.occurred_at))
        .limit(min(limit, 500))
    )
    if kind:
        stmt = stmt.where(EndpointAgentEvent.kind == kind)
    if device_id:
        stmt = stmt.where(EndpointAgentEvent.device_id == device_id)

    rows = (await db.execute(stmt)).all()
    by_kind: dict[str, int] = {}
    items: list[EAEventOut] = []
    for evt, hostname in rows:
        by_kind[evt.kind] = by_kind.get(evt.kind, 0) + 1
        items.append(EAEventOut(
            id=evt.id, device_id=evt.device_id, kind=evt.kind,
            occurred_at=evt.occurred_at, ingested_at=evt.ingested_at,
            payload=evt.payload or {}, hostname=hostname,
        ))
    return EAEventListResponse(items=items, by_kind=by_kind, total=len(items))


# --------------------------------------------------------------------
# Agent-facing endpoints — not gated by JWT
# --------------------------------------------------------------------

# `enroll` lives on the admin router prefix so all EA paths share a
# /v1/endpoint-agent/* namespace. Gating differs: enroll is anonymous
# but requires a one-time admin-minted code; ingest requires the agent
# token.
agent_router = APIRouter(prefix="/endpoint-agent", tags=["endpoint-agent-bootstrap"])


@agent_router.post("/enroll", response_model=EnrollmentResponse)
async def enroll(req: EnrollmentRequest) -> EnrollmentResponse:
    info = _ENROLLMENT_CODES.pop(req.enrollment_code, None)
    if info is None:
        raise HTTPException(status_code=401, detail="Unknown or already-consumed enrollment code")
    tenant_id, expires = info
    if expires < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Enrollment code expired")

    # We don't yet know the device_id — Postgres mints it on insert.
    # Open a non-RLS session because the agent has no tenant context
    # yet; we'll write the tenant_id explicitly.
    async with SessionLocal() as session:
        device = EndpointDevice(
            tenant_id=tenant_id, hostname=req.hostname,
            os=req.os, arch=req.arch, agent_version=req.agent_version,
            enrollment_fingerprint="pending",  # rewritten after token mint
        )
        session.add(device)
        await session.flush()
        await session.refresh(device)
        token = mint_device_token(tenant_id=tenant_id, device_id=device.id)
        device.enrollment_fingerprint = token_fingerprint(token)
        await session.commit()

    return EnrollmentResponse(
        device_id=device.id,
        agent_token=token,
        ingest_url="/v1/ingest/endpoint-agent",
        heartbeat_seconds=60,
    )


# --------------------------------------------------------------------
# Ingest endpoint — agent calls this with Bearer <agent_token>
# --------------------------------------------------------------------

ingest_router = APIRouter(prefix="/ingest", tags=["ingest"])


# Allow-listed payload keys per event kind. Anything else is rejected
# with the offending key in `rejected_reasons` so the agent author
# notices and stops sending PII-shaped fields.
_PAYLOAD_ALLOWLIST: dict[str, set[str]] = {
    "process_exec": {
        "process_name", "process_sha256", "parent_process_name",
        "parent_process_sha256", "command_line_sha256",
    },
    "file_write_to_watched_path": {
        "path_pattern", "event_type", "new_mode", "content_sha256",
    },
    "secret_read_by_ai_proc": {
        "path_pattern", "process_name", "process_sha256",
    },
    "curl_pipe_sh_detected": {
        "parent_process_name", "originating_domain", "process_tree_depth",
    },
    "mcp_config_observed": {
        "config_path_pattern", "servers", "max_scope_depth",
    },
    "package_install_pre_hook": {
        "package_name", "package_version", "ecosystem", "installer_sha256",
    },
    "path_shadow_detected": {
        "binary_name", "shadow_path", "shadow_sha256",
    },
    "autostart_artifact": {
        "artifact_path_pattern", "exec_name", "exec_sha256",
    },
    "heartbeat": {
        "uptime_seconds", "agent_version",
    },
}

# Keys that, if present in any payload, indicate a likely PII leak.
# We reject the whole event with `pii_shaped_key:<name>` so the agent
# author has a clear signal during integration testing.
_PII_DENYLIST = {
    "prompt", "email", "username", "user", "password", "body", "content",
    "url", "path", "query", "command_line",  # bare path/command-line forbidden
    "request_body", "response_body", "stdin", "stdout", "stderr",
    "messages", "chat_history",
}


def _validate_payload(kind: str, payload: dict) -> str | None:
    """Returns None if OK, else a short reason string for rejected_reasons."""
    if not isinstance(payload, dict):
        return "payload_not_object"
    for k in payload:
        if k in _PII_DENYLIST:
            return f"pii_shaped_key:{k}"
    allowed = _PAYLOAD_ALLOWLIST.get(kind, set())
    extra = set(payload.keys()) - allowed
    if extra:
        return f"unexpected_keys:{','.join(sorted(extra))}"
    return None


@ingest_router.post("/endpoint-agent", response_model=IngestReceipt)
async def ingest_ea_batch(
    batch: EABatch,
    authorization: Annotated[str | None, Header()] = None,
) -> IngestReceipt:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = verify_device_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}") from exc

    tenant_id = UUID(claims["tenant_id"])
    device_id_from_token = UUID(claims["device_id"])
    if device_id_from_token != batch.device_id:
        raise HTTPException(status_code=403, detail="Token device_id mismatch")

    fingerprint = token_fingerprint(token)
    accepted = 0
    rejected = 0
    reasons: list[str] = []
    now = datetime.now(timezone.utc)

    # Open a tenant-scoped RLS session (set_local set_config done by
    # session_scope) so the rows we write are guarded by RLS.
    async with session_scope(tenant_id=tenant_id) as session:
        device = (await session.execute(
            select(EndpointDevice).where(EndpointDevice.id == device_id_from_token)
        )).scalar_one_or_none()
        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")
        if device.enrollment_fingerprint != fingerprint:
            # Token does not match the active enrolment — possible
            # leaked/old token. Reject without leaking which one.
            raise HTTPException(status_code=401, detail="Token revoked or replaced")
        if device.revoked_at is not None:
            raise HTTPException(status_code=403, detail="Device has been revoked")

        # heartbeat — bumped on every batch
        device.last_heartbeat_at = now

        for evt in batch.events:
            reason = _validate_payload(evt.kind, evt.payload)
            if reason is not None:
                rejected += 1
                reasons.append(f"{evt.kind}:{reason}")
                continue
            session.add(EndpointAgentEvent(
                tenant_id=tenant_id, device_id=device.id,
                kind=evt.kind, occurred_at=evt.occurred_at,
                payload=evt.payload,
            ))
            accepted += 1

    return IngestReceipt(
        accepted=accepted, rejected=rejected,
        rejected_reasons=reasons[:25],   # cap to keep response bounded
        heartbeat_seconds=60,
    )
