"""Ingest endpoints — accept log batches from any registered source.

Authentication: shared ingest API key via ``X-Ingest-Key`` header. The tenant
is passed in the payload (the ingest path is machine-to-machine and not
user-scoped, so we deliberately avoid the JWT path).

Behaviour:
  - Small batches (< 200 events) are processed inline so the caller sees the
    matched + shadow_new counts immediately.
  - Larger batches are queued to Celery and return 202 with ``queued: true``.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.core.deps import verify_ingest_key
from app.integrations.network.base import registered_sources
from app.schemas.ingest import IngestBatch, IngestResponse, MatcherStats
from app.workers.ingest import process_batch
from app.workers.tasks import process_log_batch

router = APIRouter(prefix="/ingest", tags=["ingest"])

INLINE_BATCH_LIMIT = 200


@router.post("/network", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_network(
    payload: IngestBatch,
    _key: Annotated[None, Depends(verify_ingest_key)],
) -> IngestResponse:
    """Generic ingest endpoint for Proxy/CASB/NGFW/DNS sources.

    The ``source`` field selects the registered normalizer (zscaler_nss,
    netskope, squid, paloalto, fortinet, sophos_firewall, checkpoint,
    cisco_umbrella, cloudflare_gateway, …).
    """
    return await _dispatch(payload)


@router.post("/xdr", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_xdr(
    payload: IngestBatch,
    _key: Annotated[None, Depends(verify_ingest_key)],
) -> IngestResponse:
    """Ingest endpoint for XDR/EDR push (CrowdStrike, SentinelOne, Sophos XDR,
    Trellix, Seqrite, Cortex XDR, Cisco XDR). Same pipeline as /network — the
    separate route exists for routing/rate-limit policy."""
    return await _dispatch(payload)


@router.get("/sources", response_model=MatcherStats)
async def list_sources(_key: Annotated[None, Depends(verify_ingest_key)]) -> MatcherStats:
    """Diagnostic — every registered normalizer + matcher size."""
    from app.integrations.network.matcher import matcher_size
    return MatcherStats(**matcher_size(), sources=registered_sources())


async def _dispatch(payload: IngestBatch) -> IngestResponse:
    if not payload.events:
        raise HTTPException(status_code=400, detail="Empty event batch")

    if len(payload.events) <= INLINE_BATCH_LIMIT:
        result = await process_batch(
            tenant_id=payload.tenant_id,
            source=payload.source,
            events=payload.events,
        )
        return IngestResponse(
            accepted=result["accepted"],
            queued=False,
            matched=result["matched"],
            shadow_new=result["shadow_new"],
        )

    # Hand off to Celery for large batches.
    process_log_batch.delay(str(payload.tenant_id), payload.source, payload.events)
    return IngestResponse(accepted=len(payload.events), queued=True)
