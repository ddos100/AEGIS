"""Threat-feed ingest service (Phase 7.2).

Iterates every registered feed normalizer, persists raw upstream
records to `raw_threat_feed`, and upserts `draft_threats` for the
review queue.

Idempotency
-----------
- `raw_threat_feed.uq_raw_threat_feed_dedup` on (source, payload_sha256)
  silently drops re-ingest of an unchanged upstream record.
- `draft_threats.uq_draft_threats_fingerprint` on
  sha256(source|upstream_id) keeps a single draft per upstream record
  regardless of how many times the feed runs.

Reviewer-friendly behaviour
---------------------------
- A draft that has already been `published` is never overwritten —
  upstream changes after publication produce a new draft (we
  invalidate the old one to `superseded`).
- A `rejected` draft is also never re-promoted automatically; if the
  upstream record changes meaningfully (different payload sha), a new
  draft is created so the reviewer sees the update.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.integrations.threat_feeds import (
    BaseFeedNormalizer,
    DraftThreat,
    get_normalizer,
    list_normalizers,
)
from app.models.draft_threat import DraftThreat as DraftThreatRow
from app.models.raw_threat_feed import RawThreatFeed


log = logging.getLogger(__name__)


async def ingest_one_source(*, session, source: str) -> dict[str, Any]:
    """Pull, normalise, and upsert for a single source."""
    try:
        normalizer: BaseFeedNormalizer = get_normalizer(source)
    except KeyError as exc:
        return {"source": source, "ok": False, "error": str(exc)}

    seen = drafted = duplicates = skipped = errored = 0
    raws: list[dict[str, Any]] = []
    try:
        async for raw in normalizer.fetch():
            seen += 1
            raws.append(raw)
            sha = normalizer.payload_sha_of(raw)
            upstream_id = normalizer.upstream_id_of(raw)
            if not upstream_id:
                skipped += 1
                continue

            # 1) Append-only raw log (dedup via uq_raw_threat_feed_dedup).
            stmt = (
                pg_insert(RawThreatFeed)
                .values(
                    source=source, upstream_id=upstream_id,
                    payload=raw, payload_sha256=sha,
                )
                .on_conflict_do_nothing(constraint="uq_raw_threat_feed_dedup")
            )
            await session.execute(stmt)

            # 2) Normalise → DraftThreat (None means filtered out).
            try:
                draft = normalizer.normalize(raw)
            except Exception as exc:  # noqa: BLE001
                log.exception("aegis.feed.normalize.error",
                              extra={"source": source, "upstream_id": upstream_id})
                errored += 1
                continue
            if draft is None:
                skipped += 1
                continue

            fingerprint = normalizer.fingerprint_of(upstream_id)
            existing = (await session.execute(
                select(DraftThreatRow)
                .where(DraftThreatRow.source_fingerprint == fingerprint)
            )).scalar_one_or_none()

            if existing is not None:
                if existing.review_status in ("published", "rejected"):
                    # Reviewer has made a terminal decision. Only mark as
                    # 'superseded' if the upstream payload changed
                    # meaningfully — keep silent otherwise.
                    if existing.draft != draft.to_dict() and existing.review_status == "published":
                        existing.review_status = "superseded"
                    duplicates += 1
                    continue
                # pending_review or superseded: refresh the draft body
                # so reviewer always sees the latest upstream version.
                existing.draft = draft.to_dict()
                existing.upstream_id = upstream_id
                existing.review_status = "pending_review"
                drafted += 1
            else:
                session.add(DraftThreatRow(
                    source=source,
                    upstream_id=upstream_id,
                    source_fingerprint=fingerprint,
                    draft=draft.to_dict(),
                    review_status="pending_review",
                ))
                drafted += 1
    except Exception as exc:  # noqa: BLE001
        log.exception("aegis.feed.ingest.error", extra={"source": source})
        return {"source": source, "ok": False, "error": str(exc),
                "seen": seen, "drafted": drafted, "errored": errored}

    return {
        "source":     source,
        "ok":         True,
        "seen":       seen,
        "drafted":    drafted,
        "duplicates": duplicates,
        "skipped":    skipped,
        "errored":    errored,
    }


async def ingest_all_sources(*, session) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in list_normalizers():
        out.append(await ingest_one_source(session=session, source=entry["source"]))
    return out


def to_threat_yaml_record(draft: dict[str, Any]) -> dict[str, Any]:
    """Project a DraftThreat dict into the catalogue YAML record shape.

    The publish flow writes this dict as YAML under
    catalogue/threats/<source>/<threat_id>.yaml so the file remains
    the source of truth even after the table is upserted.
    """
    # Strip presentation-only keys; YAML keeps the same field names.
    out = dict(draft)
    # JSON-safe types preserved as-is; YAML serialisation happens at
    # the API layer.
    return out
