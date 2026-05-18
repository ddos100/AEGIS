"""Threat-feed review queue endpoints (Phase 7.2).

Mounted under /v1/threats/feed/... — separate from the catalogue
browse router so the feed surface is clearly distinguished and gated
on admin role (publish/reject) where the catalogue routes are
analyst-readable.

All routes are gated by `requires_module("AEGIS-THREAT")` — feed
ingest is part of the same SKU as the catalogue.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

import yaml
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.core.deps import CurrentUser, DBSession, require_admin
from app.core.licence import requires_module
from app.integrations.threat_feeds import list_normalizers
from app.models.draft_threat import DraftThreat as DraftThreatRow
from app.models.threat import Threat
from app.schemas.threat_feed import (
    DraftBrief,
    DraftDecisionRequest,
    DraftDetail,
    DraftListResponse,
    FeedSourceInfo,
    IngestRunResult,
    PublishRequest,
)


router = APIRouter(
    prefix="/threats/feed",
    tags=["threats-feed"],
    dependencies=[Depends(requires_module("AEGIS-THREAT"))],
)


def _safe_uuid(value: str | UUID | None) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(value)
    except (ValueError, TypeError):
        return None


def _to_brief(row: DraftThreatRow) -> DraftBrief:
    d = row.draft or {}
    return DraftBrief(
        id=row.id, source=row.source, upstream_id=row.upstream_id,
        review_status=row.review_status, ingested_at=row.ingested_at,
        reviewed_at=row.reviewed_at,
        threat_id=str(d.get("threat_id") or row.upstream_id),
        title=str(d.get("title") or "(no title)")[:200],
        severity=str(d.get("severity") or "medium"),
        classes=list(d.get("classes") or []),
        vectors=list(d.get("vectors") or []),
    )


# ---------------------------------------------------------------------------
# Inventory + listing
# ---------------------------------------------------------------------------

@router.get("/sources", response_model=list[FeedSourceInfo])
async def list_sources(user: CurrentUser):  # noqa: ARG001
    return [FeedSourceInfo(**s) for s in list_normalizers()]


@router.get("/pending-review", response_model=DraftListResponse)
async def list_pending(
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
):
    """All drafts the reviewer should look at — pending_review +
    superseded. Sort by ingested_at desc."""
    rows = (await db.execute(
        select(DraftThreatRow)
        .where(DraftThreatRow.review_status.in_(("pending_review", "superseded")))
        .order_by(DraftThreatRow.ingested_at.desc())
        .limit(500)
    )).scalars().all()
    by_status: dict[str, int] = {}
    items: list[DraftBrief] = []
    for r in rows:
        by_status[r.review_status] = by_status.get(r.review_status, 0) + 1
        items.append(_to_brief(r))
    return DraftListResponse(items=items, by_status=by_status, total=len(items))


@router.get("/drafts/{draft_id}", response_model=DraftDetail)
async def get_draft(
    draft_id: UUID,
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
):
    row = (await db.execute(
        select(DraftThreatRow).where(DraftThreatRow.id == draft_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    brief = _to_brief(row)
    return DraftDetail(
        **brief.model_dump(),
        draft=row.draft or {},
        review_notes=row.review_notes,
        source_fingerprint=row.source_fingerprint,
        published_threat_id=row.published_threat_id,
    )


# ---------------------------------------------------------------------------
# Manual refresh
# ---------------------------------------------------------------------------

@router.post("/refresh", response_model=list[IngestRunResult])
async def refresh_now(
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],  # noqa: ARG001
):
    """Admin trigger to run every feed normalizer right now without
    waiting for the hourly beat. Returns per-source counts."""
    from app.services.threat_feed_ingest import ingest_all_sources
    results = await ingest_all_sources(session=db)
    return [IngestRunResult(**r) for r in results]


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

CATALOGUE_DIR = Path(__file__).resolve().parents[3] / "catalogue" / "threats"


@router.post("/drafts/{draft_id}/publish", response_model=DraftDetail)
async def publish_draft(
    draft_id: UUID,
    payload: PublishRequest,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],
):
    """Approve a draft. Writes the canonical record to `threats` AND
    (when write_yaml=True) emits a YAML file the importer + digest
    pipeline can re-read for determinism guarantees.

    The draft must declare a non-empty `exposure_check` predicate map —
    AEGIS will not accept a paper-only entry into the catalogue. This
    is the same "testable only" rule the Compliance module already
    enforces.
    """
    row = (await db.execute(
        select(DraftThreatRow).where(DraftThreatRow.id == draft_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    if row.review_status not in ("pending_review", "superseded"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot publish from status={row.review_status!r}",
        )
    body = payload.edited_draft or row.draft or {}
    if not (body.get("exposure_check") or {}):
        raise HTTPException(
            status_code=422,
            detail="Refusing to publish: exposure_check is empty. Every threat "
                    "in the AEGIS catalogue MUST declare at least one predicate.",
        )
    # Required-field sanity check (extra guard beyond DB constraints).
    for required in ("threat_id", "title", "source_ref", "verbatim_description",
                     "severity", "classes", "vectors"):
        if not body.get(required):
            raise HTTPException(
                status_code=422,
                detail=f"Refusing to publish: missing required field {required!r}",
            )

    # 1) Upsert into the canonical threats table.
    threat_id_str = body["threat_id"]
    existing = (await db.execute(
        select(Threat).where(Threat.threat_id == threat_id_str)
    )).scalar_one_or_none()
    last_updated_value = body.get("last_updated")
    if isinstance(last_updated_value, str):
        try:
            last_updated_value = date.fromisoformat(last_updated_value)
        except ValueError:
            last_updated_value = date.today()
    elif last_updated_value is None:
        last_updated_value = date.today()

    if existing is None:
        existing = Threat(
            threat_id=threat_id_str,
            title=body["title"],
            source_ref=body["source_ref"],
            verbatim_description=body["verbatim_description"],
            description=body.get("description"),
            severity=body["severity"],
            classes=list(body["classes"]),
            vectors=list(body["vectors"]),
            mitre_atlas_ids=list(body.get("mitre_atlas_ids") or []),
            owasp_llm_ids=list(body.get("owasp_llm_ids") or []),
            sector_amplifiers=list(body.get("sector_amplifiers") or []),
            applies_to_jurisdictions=list(body.get("applies_to_jurisdictions") or ["global"]),
            exposure_check=body["exposure_check"],
            mitigation=body.get("mitigation"),
            evidence_hints=list(body.get("evidence_hints") or []),
            compliance_implications=list(body.get("compliance_implications") or []),
            catalogue_version=body.get("catalogue_version", "1.0.0"),
            last_updated=last_updated_value,
        )
        db.add(existing)
    else:
        existing.title = body["title"]
        existing.source_ref = body["source_ref"]
        existing.verbatim_description = body["verbatim_description"]
        existing.description = body.get("description")
        existing.severity = body["severity"]
        existing.classes = list(body["classes"])
        existing.vectors = list(body["vectors"])
        existing.mitre_atlas_ids = list(body.get("mitre_atlas_ids") or [])
        existing.owasp_llm_ids = list(body.get("owasp_llm_ids") or [])
        existing.sector_amplifiers = list(body.get("sector_amplifiers") or [])
        existing.applies_to_jurisdictions = list(body.get("applies_to_jurisdictions") or ["global"])
        existing.exposure_check = body["exposure_check"]
        existing.mitigation = body.get("mitigation")
        existing.evidence_hints = list(body.get("evidence_hints") or [])
        existing.compliance_implications = list(body.get("compliance_implications") or [])
        existing.catalogue_version = body.get("catalogue_version", existing.catalogue_version)
        existing.last_updated = last_updated_value
    await db.flush()
    await db.refresh(existing)

    # 2) Write the YAML file so catalogue/threats/* remains the source
    # of truth + the importer + digest pipeline still works on a
    # `make threats-import` + drift check.
    yaml_written: str | None = None
    if payload.write_yaml:
        try:
            subdir = CATALOGUE_DIR / row.source
            subdir.mkdir(parents=True, exist_ok=True)
            target = subdir / f"{threat_id_str}.yaml"
            # Convert date objects so PyYAML doesn't choke.
            doc = dict(body)
            if isinstance(doc.get("last_updated"), date):
                doc["last_updated"] = doc["last_updated"].isoformat()
            yaml_text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
            target.write_text(yaml_text, encoding="utf-8")
            yaml_written = str(target.relative_to(CATALOGUE_DIR.parent.parent))
        except OSError:
            # Read-only filesystem (e.g. an immutable container). Treat
            # as soft-fail: DB row is still authoritative; the deploy
            # operator can re-emit the YAML out of band.
            yaml_written = None

    # 3) Mark draft published.
    row.review_status = "published"
    row.published_threat_id = existing.id
    row.review_notes = payload.notes
    row.reviewed_by = _safe_uuid(user.sub)
    row.reviewed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(row)

    brief = _to_brief(row)
    detail = DraftDetail(
        **brief.model_dump(),
        draft=row.draft or {},
        review_notes=(yaml_written and f"yaml: {yaml_written}\n") or "" + (row.review_notes or ""),
        source_fingerprint=row.source_fingerprint,
        published_threat_id=row.published_threat_id,
    )
    return detail


@router.post("/drafts/{draft_id}/reject", response_model=DraftDetail)
async def reject_draft(
    draft_id: UUID,
    payload: DraftDecisionRequest,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],
):
    row = (await db.execute(
        select(DraftThreatRow).where(DraftThreatRow.id == draft_id)
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Draft not found")
    if row.review_status not in ("pending_review", "superseded"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot reject from status={row.review_status!r}",
        )
    row.review_status = "rejected"
    row.review_notes = payload.notes
    row.reviewed_by = _safe_uuid(user.sub)
    row.reviewed_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(row)
    brief = _to_brief(row)
    return DraftDetail(
        **brief.model_dump(),
        draft=row.draft or {},
        review_notes=row.review_notes,
        source_fingerprint=row.source_fingerprint,
        published_threat_id=row.published_threat_id,
    )
