"""Cloudflare Zero Trust Gateway — Logpush HTTP/DNS event normalizer.

Cloudflare Gateway Logpush emits NDJSON with fields including:
  EventTimestamp, UserEmail, DeviceID, ResolvedIPs, QueryName, DNSResponse,
  Action, BlockedCategoryNames, HTTPHost, HTTPStatusCode
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.integrations.network.base import BaseNormalizer, NormalizedEvent, register


@register("cloudflare_gateway", vector="network_telemetry")
class CloudflareGatewayNormalizer(BaseNormalizer):
    def parse(self, raw: Any) -> NormalizedEvent | None:
        if not isinstance(raw, dict):
            return None
        host = (raw.get("HTTPHost") or raw.get("QueryName") or "").lower().rstrip(".").strip() or None
        if not host:
            return None
        return NormalizedEvent(
            occurred_at=self._parse_time(raw.get("EventTimestamp") or raw.get("Datetime")),
            vector="network_telemetry",
            source="cloudflare_gateway",
            domain=host,
            user_email=(raw.get("UserEmail") or "").lower() or None,
            source_ip=raw.get("SourceIP") or raw.get("ResolverIP"),
            hostname=raw.get("DeviceName"),
            raw_meta={
                "action": raw.get("Action"),
                "blocked_categories": raw.get("BlockedCategoryNames"),
                "policy_id": raw.get("PolicyID"),
                "device_id": raw.get("DeviceID"),
            },
        )

    @staticmethod
    def _parse_time(value: Any) -> datetime:
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                pass
        if isinstance(value, (int, float)):
            v = float(value)
            if v > 10**12:
                v /= 1000
            return datetime.fromtimestamp(v, tz=timezone.utc)
        return datetime.now(timezone.utc)
