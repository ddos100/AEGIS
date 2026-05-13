"""Generic OCSF v1.x JSON normalizer — catch-all for any SIEM/vendor that
emits Open Cybersecurity Schema Framework events.

Supports the two OCSF classes most relevant to AEGIS discovery:
  - 4001  Network Activity
  - 4002  HTTP Activity
  - 1001/1002  Process Activity (used by XDR sources for desktop AI agents)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.integrations.network.base import BaseNormalizer, NormalizedEvent, register


@register("ocsf", vector="network_telemetry")
class OCSFNormalizer(BaseNormalizer):
    def parse(self, raw: Any) -> NormalizedEvent | None:
        if not isinstance(raw, dict):
            return None
        cls = raw.get("class_uid") or raw.get("class")
        if cls in (1001, 1002, "Process Activity"):
            return self._parse_process(raw)
        # Default: network/HTTP activity
        http = raw.get("http_request") or {}
        url = http.get("url") if isinstance(http, dict) else None
        url_str = url.get("url_string") if isinstance(url, dict) else url
        host, path = self._split_url(url_str if isinstance(url_str, str) else
                                     raw.get("dst_endpoint", {}).get("hostname"))
        if not host:
            return None

        actor_user = (raw.get("actor", {}) or {}).get("user", {}) or {}
        traffic = raw.get("traffic", {}) or {}
        src = raw.get("src_endpoint", {}) or {}

        return NormalizedEvent(
            occurred_at=self._parse_time(raw.get("time")),
            vector="network_telemetry",
            source="ocsf",
            domain=host,
            url_path=path,
            user_email=(actor_user.get("email_addr") or "").strip().lower() or None,
            department=(actor_user.get("org") or {}).get("name") if isinstance(actor_user.get("org"), dict) else None,
            source_ip=src.get("ip"),
            hostname=src.get("hostname"),
            bytes_sent=self._safe_int(traffic.get("bytes_out")),
            bytes_recv=self._safe_int(traffic.get("bytes_in")),
            raw_meta={"disposition": raw.get("disposition"), "class_uid": cls},
        )

    def _parse_process(self, raw: dict[str, Any]) -> NormalizedEvent | None:
        proc = raw.get("process") or {}
        name = proc.get("name") or proc.get("file", {}).get("name")
        if not name:
            return None
        # Process events carry no domain — the matcher will look at process_name
        # (matched separately against the catalogue's known-AI-desktop list).
        return NormalizedEvent(
            occurred_at=self._parse_time(raw.get("time")),
            vector="xdr_edr",
            source="ocsf",
            process_name=name,
            process_hash=(proc.get("file") or {}).get("hashes", [{}])[0].get("value")
                          if isinstance(proc.get("file"), dict) else None,
            user_email=((raw.get("actor", {}) or {}).get("user", {}) or {}).get("email_addr"),
            hostname=(raw.get("device", {}) or {}).get("hostname"),
            raw_meta={"cmdline": proc.get("cmd_line"), "class_uid": raw.get("class_uid")},
        )

    @staticmethod
    def _parse_time(value: Any) -> datetime:
        if isinstance(value, (int, float)):
            v = float(value)
            if v > 10**12:
                v /= 1000
            return datetime.fromtimestamp(v, tz=timezone.utc)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                pass
        return datetime.now(timezone.utc)
