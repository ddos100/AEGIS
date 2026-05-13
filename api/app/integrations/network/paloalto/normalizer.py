"""Palo Alto PAN-OS Traffic + DNS log normalizer.

Accepts:
  - PAN-OS LEEF / CSV syslog dicts (one log entry already parsed by the upstream
    syslog collector into a key/value dict). Field names mirror PAN-OS Traffic
    + URL Filtering logs.
  - PAN-OS OCSF export (delegated to OCSFNormalizer via shared helpers).

For raw CEF lines, register the source as ``cef`` upstream — the CEF normalizer
handles vendor "Palo Alto Networks" generically.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.integrations.network.base import BaseNormalizer, NormalizedEvent, register


@register("paloalto", vector="network_telemetry")
class PaloAltoNormalizer(BaseNormalizer):
    def parse(self, raw: Any) -> NormalizedEvent | None:
        if not isinstance(raw, dict):
            return None
        # PAN-OS URL/Traffic logs: subtype hints which schema we have.
        url = raw.get("url") or raw.get("misc")
        host = (raw.get("hostname") or raw.get("dst_host") or raw.get("dest_host"))
        host_from_url, path = self._split_url(url) if url else (None, None)
        host = (host_from_url or host or "").lower().strip() or None
        if not host:
            return None

        return NormalizedEvent(
            occurred_at=self._parse_time(raw.get("time_generated") or raw.get("receive_time") or raw.get("time")),
            vector="network_telemetry",
            source="paloalto",
            domain=host,
            url_path=path,
            user_email=(raw.get("src_user") or raw.get("user") or "").lower() or None,
            department=raw.get("user_group"),
            source_ip=raw.get("src_ip") or raw.get("src"),
            bytes_sent=self._safe_int(raw.get("bytes_sent")),
            bytes_recv=self._safe_int(raw.get("bytes_received")),
            raw_meta={
                "action": raw.get("action"),
                "app": raw.get("app") or raw.get("application"),
                "category": raw.get("category"),
                "session_end_reason": raw.get("session_end_reason"),
            },
        )

    @staticmethod
    def _parse_time(value: Any) -> datetime:
        if isinstance(value, str):
            for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
                try:
                    dt = datetime.strptime(value, fmt)
                    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
                except ValueError:
                    continue
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
