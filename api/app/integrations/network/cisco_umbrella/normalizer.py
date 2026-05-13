"""Cisco Umbrella (OpenDNS) DNS log normalizer.

Umbrella CSV-formatted DNS log columns (S3 export):

    timestamp, identities, internal_ip, external_ip, action,
    query_type, response_code, domain, categories, policy_identity

Accepts either a tokenised dict or a CSV-parsed dict — Umbrella S3 exports
populate keys directly when parsed by an upstream collector.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.integrations.network.base import BaseNormalizer, NormalizedEvent, register


@register("cisco_umbrella", vector="network_telemetry")
class CiscoUmbrellaNormalizer(BaseNormalizer):
    def parse(self, raw: Any) -> NormalizedEvent | None:
        if not isinstance(raw, dict):
            return None
        host = (raw.get("domain") or raw.get("Domain") or "").lower().rstrip(".").strip() or None
        if not host:
            return None
        return NormalizedEvent(
            occurred_at=self._parse_time(raw.get("timestamp") or raw.get("Timestamp")),
            vector="network_telemetry",
            source="cisco_umbrella",
            domain=host,
            user_email=raw.get("identities") or raw.get("identity"),
            source_ip=raw.get("internal_ip") or raw.get("InternalIP"),
            raw_meta={
                "action": raw.get("action") or raw.get("Action"),
                "query_type": raw.get("query_type"),
                "response_code": raw.get("response_code"),
                "categories": raw.get("categories"),
            },
        )

    @staticmethod
    def _parse_time(value: Any) -> datetime:
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                pass
            for fmt in ("%Y-%m-%d %H:%M:%S",):
                try:
                    return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
        if isinstance(value, (int, float)):
            v = float(value)
            if v > 10**12:
                v /= 1000
            return datetime.fromtimestamp(v, tz=timezone.utc)
        return datetime.now(timezone.utc)
