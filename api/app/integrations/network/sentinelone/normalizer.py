"""SentinelOne Singularity XDR — REST API (Deep Visibility JSON shape).

Singularity also emits CEF over syslog; that path is covered by the generic
CEF normalizer (source="cef"). This normalizer handles the native REST DV
events which carry richer fields (process tree, tgtFileSha256, etc).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.integrations.network.base import BaseNormalizer, NormalizedEvent, register


@register("sentinelone", vector="xdr_edr")
class SentinelOneNormalizer(BaseNormalizer):
    def parse(self, raw: Any) -> NormalizedEvent | None:
        if not isinstance(raw, dict):
            return None
        # SentinelOne wraps the payload under "event" or returns it flat.
        e = raw.get("event") or raw

        event_type = e.get("eventType") or e.get("event_type")
        # DNS event family
        if event_type in ("DNSAction", "DNS Request"):
            host = (e.get("dns.request") or e.get("dnsRequest") or "").lower().strip() or None
            if not host:
                return None
            return NormalizedEvent(
                occurred_at=self._parse_time(e.get("eventTime") or e.get("createdAt")),
                vector="xdr_edr",
                source="sentinelone",
                domain=host,
                user_email=e.get("loginUser") or e.get("userName"),
                hostname=e.get("endpointName") or e.get("agentName"),
                process_name=e.get("processName") or e.get("srcProcName"),
                process_hash=e.get("srcProcessSha256") or e.get("processImageSha256"),
                raw_meta={"event_type": event_type, "policy_action": e.get("policyAction")},
            )
        # Network connection — IP plus often a resolved name
        if event_type in ("IP Connect", "IP Listen", "Network Action"):
            host = (e.get("dstHost") or e.get("dstIp") or "").lower().strip() or None
            if not host:
                return None
            return NormalizedEvent(
                occurred_at=self._parse_time(e.get("eventTime") or e.get("createdAt")),
                vector="xdr_edr",
                source="sentinelone",
                domain=host,
                user_email=e.get("loginUser"),
                hostname=e.get("endpointName"),
                process_name=e.get("processName"),
                process_hash=e.get("processImageSha256"),
                source_ip=e.get("srcIp"),
                bytes_sent=self._safe_int(e.get("bytesSent")),
                bytes_recv=self._safe_int(e.get("bytesReceived")),
                raw_meta={"event_type": event_type, "dst_port": e.get("dstPort")},
            )
        # Process launch
        if event_type in ("Process Creation",):
            name = (e.get("processName") or "").lower() or None
            if not name:
                return None
            return NormalizedEvent(
                occurred_at=self._parse_time(e.get("eventTime")),
                vector="xdr_edr",
                source="sentinelone",
                process_name=name,
                process_hash=e.get("processImageSha256"),
                user_email=e.get("loginUser"),
                hostname=e.get("endpointName"),
                raw_meta={"event_type": event_type, "cmdline": e.get("commandLine")},
            )
        return None

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
