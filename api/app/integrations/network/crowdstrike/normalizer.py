"""CrowdStrike Falcon Streaming API normalizer.

Falcon emits two event families relevant to AEGIS:
  - DetectionSummaryEvent  / behavioural detection (AI desktop apps, code
                            assistants spawning on managed endpoints).
  - DnsRequest / NetworkConnectIP4 process telemetry (network destinations
                            including AI service domains).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.integrations.network.base import BaseNormalizer, NormalizedEvent, register


@register("crowdstrike", vector="xdr_edr")
class CrowdStrikeNormalizer(BaseNormalizer):
    def parse(self, raw: Any) -> NormalizedEvent | None:
        if not isinstance(raw, dict):
            return None
        meta = raw.get("metadata") or {}
        event = raw.get("event") or raw
        event_type = meta.get("eventType") or event.get("eventType")

        # 1. DNS request — domain visible directly
        if event_type in ("DnsRequest", "DnsRequestMacV1", "DnsRequestWindows"):
            host = (event.get("DomainName") or "").lower().strip() or None
            if not host:
                return None
            return NormalizedEvent(
                occurred_at=self._epoch_or_iso(event.get("ContextTimeStamp") or meta.get("eventCreationTime")),
                vector="xdr_edr",
                source="crowdstrike",
                domain=host,
                user_email=event.get("UserName"),
                hostname=event.get("ComputerName"),
                process_name=event.get("ImageFileName") or event.get("ProcessName"),
                process_hash=event.get("SHA256HashData"),
                source_ip=event.get("aip"),
                raw_meta={"event_type": event_type, "request_type": event.get("RequestType")},
            )
        # 2. NetworkConnect with remote host name from sensor
        if event_type in ("NetworkConnectIP4", "NetworkConnectIP6"):
            host = (event.get("RemoteAddressIP4") or event.get("RemoteAddressIP6") or "").lower()
            domain = event.get("RemoteHostName") or None
            if not domain and not host:
                return None
            return NormalizedEvent(
                occurred_at=self._epoch_or_iso(event.get("ContextTimeStamp")),
                vector="xdr_edr",
                source="crowdstrike",
                domain=(domain or host).lower(),
                user_email=event.get("UserName"),
                hostname=event.get("ComputerName"),
                process_name=event.get("ImageFileName"),
                process_hash=event.get("SHA256HashData"),
                source_ip=event.get("aip"),
                bytes_sent=self._safe_int(event.get("BytesSent")),
                bytes_recv=self._safe_int(event.get("BytesReceived")),
                raw_meta={"event_type": event_type, "remote_port": event.get("RemotePort")},
            )
        # 3. ProcessRollup2 / desktop AI app launch
        if event_type in ("ProcessRollup2", "SyntheticProcessRollup2"):
            name = (event.get("ImageFileName") or "").lower()
            if not name:
                return None
            return NormalizedEvent(
                occurred_at=self._epoch_or_iso(event.get("ContextTimeStamp")),
                vector="xdr_edr",
                source="crowdstrike",
                process_name=name,
                process_hash=event.get("SHA256HashData"),
                user_email=event.get("UserName"),
                hostname=event.get("ComputerName"),
                raw_meta={"event_type": event_type, "cmdline": event.get("CommandLine")},
            )
        return None

    @staticmethod
    def _epoch_or_iso(value: Any) -> datetime:
        if isinstance(value, (int, float)):
            v = float(value)
            if v > 10**12:
                v /= 1000
            elif v > 10**10:
                v /= 1000  # CrowdStrike often uses ms
            return datetime.fromtimestamp(v, tz=timezone.utc)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                pass
        return datetime.now(timezone.utc)
