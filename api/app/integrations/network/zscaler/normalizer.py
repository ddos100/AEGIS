"""Zscaler ZIA (NSS feed / Nanolog Streaming Service) normalizer.

Accepts either Zscaler's native JSON shape or its OCSF v1.x export.
Fields used (NSS web log):
  user, department, url, host, urlclass, cip, sip, time,
  reqsize, respsize, action, useragent
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.integrations.network.base import BaseNormalizer, NormalizedEvent, register


@register("zscaler_nss", vector="network_telemetry")
class ZscalerNormalizer(BaseNormalizer):
    def parse(self, raw: Any) -> NormalizedEvent | None:
        if not isinstance(raw, dict):
            return None

        # Allow OCSF-shaped entries (Zscaler also emits OCSF).
        if "http_request" in raw or "actor" in raw:
            return self._parse_ocsf(raw)

        url = raw.get("url") or raw.get("host")
        if not url:
            return None
        host, path = self._split_url(url)
        if not host:
            return None

        occurred_at = self._parse_time(raw.get("time") or raw.get("datetime"))

        return NormalizedEvent(
            occurred_at=occurred_at,
            vector="network_telemetry",
            source="zscaler_nss",
            domain=host,
            url_path=path,
            user_email=(raw.get("user") or raw.get("login") or "").strip().lower() or None,
            department=raw.get("department") or raw.get("dept"),
            source_ip=raw.get("cip") or raw.get("clientip"),
            bytes_sent=self._safe_int(raw.get("reqsize") or raw.get("bytes_out")),
            bytes_recv=self._safe_int(raw.get("respsize") or raw.get("bytes_in")),
            raw_meta={
                "action":     raw.get("action"),
                "urlclass":   raw.get("urlclass"),
                "useragent":  raw.get("useragent"),
                "appname":    raw.get("appname"),
            },
        )

    def _parse_ocsf(self, raw: dict[str, Any]) -> NormalizedEvent | None:
        http = raw.get("http_request") or {}
        url_obj = http.get("url") if isinstance(http.get("url"), dict) else None
        url_str = url_obj.get("url_string") if url_obj else http.get("url")
        host, path = self._split_url(url_str if isinstance(url_str, str) else None)
        if not host:
            return None

        actor = raw.get("actor", {}).get("user", {}) or {}
        traffic = raw.get("traffic", {}) or {}
        return NormalizedEvent(
            occurred_at=self._parse_time(raw.get("time")),
            vector="network_telemetry",
            source="zscaler_nss",
            domain=host,
            url_path=path,
            user_email=(actor.get("email_addr") or "").strip().lower() or None,
            department=actor.get("org", {}).get("name") if isinstance(actor.get("org"), dict) else None,
            source_ip=raw.get("src_endpoint", {}).get("ip"),
            bytes_sent=self._safe_int(traffic.get("bytes_out")),
            bytes_recv=self._safe_int(traffic.get("bytes_in")),
            raw_meta={"disposition": raw.get("disposition")},
        )

    @staticmethod
    def _parse_time(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value.astimezone(timezone.utc)
        if isinstance(value, (int, float)):
            # NSS emits epoch seconds; OCSF emits epoch milliseconds.
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
