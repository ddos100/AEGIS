"""Generic ArcSight Common Event Format (CEF) normalizer.

CEF lines look like::

    CEF:0|Fortinet|FortiGate|7.4.0|13|allowed|3|src=10.0.1.5 dst=104.18.32.7 \
        request=https://chat.openai.com/v1/chat suser=alice@example.com out=2348 in=128

Used as the catch-all for any product emitting CEF syslog: Fortinet FortiGate,
Sophos XG firewall, Forcepoint, Check Point Log Exporter, generic Trellix, etc.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.integrations.network.base import BaseNormalizer, NormalizedEvent, register

_HEADER = re.compile(r"^CEF:\d+\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|(.*)$")
_EXT_KV = re.compile(r"([a-zA-Z][a-zA-Z0-9_]*)=((?:\\=|[^=])*?)(?=\s+[a-zA-Z][a-zA-Z0-9_]*=|$)")


def _parse_cef(line: str) -> tuple[dict[str, str], dict[str, str]] | None:
    m = _HEADER.match(line.strip())
    if not m:
        return None
    vendor, product, version, sig, name, sev, ext = m.groups()
    header = dict(vendor=vendor, product=product, version=version, signature_id=sig, name=name, severity=sev)
    extension = {k: v.replace("\\=", "=") for k, v in _EXT_KV.findall(ext)}
    return header, extension


@register("cef", vector="network_telemetry")
class CEFNormalizer(BaseNormalizer):
    def parse(self, raw: Any) -> NormalizedEvent | None:
        if isinstance(raw, dict):
            line = raw.get("message") or raw.get("raw")
        else:
            line = raw
        if not isinstance(line, str):
            return None
        parsed = _parse_cef(line)
        if not parsed:
            return None
        header, ext = parsed

        url = ext.get("request") or ext.get("requestUrl")
        host, path = self._split_url(url)
        if not host:
            host = ext.get("dhost") or ext.get("dst_host")
        if not host:
            return None
        if path is None and ext.get("requestPath"):
            path = ext["requestPath"]

        vector = "xdr_edr" if header["product"].lower() in {
            "intercept x", "central", "falcon", "singularity", "trellix"
        } else "network_telemetry"

        return NormalizedEvent(
            occurred_at=self._parse_time(ext.get("rt") or ext.get("end") or ext.get("start")),
            vector=vector,  # type: ignore[arg-type]
            source=f"cef:{header['vendor']}".lower().replace(" ", "_"),
            domain=host.lower(),
            url_path=path,
            user_email=(ext.get("suser") or ext.get("duser") or "").lower() or None,
            source_ip=ext.get("src") or ext.get("sourceIP"),
            hostname=ext.get("shost"),
            process_name=ext.get("sproc") or ext.get("processName"),
            bytes_sent=self._safe_int(ext.get("out") or ext.get("bytesOut")),
            bytes_recv=self._safe_int(ext.get("in") or ext.get("bytesIn")),
            raw_meta={"cef_vendor": header["vendor"], "cef_product": header["product"],
                      "signature_id": header["signature_id"], "name": header["name"]},
        )

    @staticmethod
    def _parse_time(value: Any) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        try:
            # CEF rt is usually epoch milliseconds.
            v = float(value)
            if v > 10**12:
                v /= 1000
            return datetime.fromtimestamp(v, tz=timezone.utc)
        except (TypeError, ValueError):
            try:
                return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
            except ValueError:
                return datetime.now(timezone.utc)
