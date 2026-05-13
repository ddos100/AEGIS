"""Squid access-log normalizer (native text format).

Native Squid access.log fields (space-separated):

    timestamp elapsed remotehost code/status bytes method URL rfc931 \
    peerstatus/peerhost type

Example::

    1715600000.123 184 10.0.1.5 TCP_TUNNEL/200 53412 CONNECT chat.openai.com:443 - HIER_DIRECT/104.18.32.7 -

The normalizer accepts either a raw line string OR a pre-tokenised dict
(useful when an upstream agent already parsed the line).
"""
from __future__ import annotations

import shlex
from datetime import datetime, timezone
from typing import Any

from app.integrations.network.base import BaseNormalizer, NormalizedEvent, register


@register("squid", vector="network_telemetry")
class SquidNormalizer(BaseNormalizer):
    def parse(self, raw: Any) -> NormalizedEvent | None:
        if isinstance(raw, dict):
            return self._parse_dict(raw)
        if not isinstance(raw, str):
            return None
        try:
            parts = shlex.split(raw)
        except ValueError:
            parts = raw.split()
        if len(parts) < 7:
            return None
        ts, _elapsed, remote_ip, _code_status, bytes_s, _method, url = parts[:7]
        rfc931 = parts[7] if len(parts) > 7 else "-"

        host, path = self._split_url(url)
        if not host:
            return None

        return NormalizedEvent(
            occurred_at=self._epoch_to_dt(ts),
            vector="network_telemetry",
            source="squid",
            domain=host,
            url_path=path,
            user_email=rfc931 if rfc931 not in ("-", "") else None,
            source_ip=remote_ip if remote_ip != "-" else None,
            bytes_recv=self._safe_int(bytes_s),
            raw_meta={"code_status": _code_status, "method": _method},
        )

    def _parse_dict(self, raw: dict[str, Any]) -> NormalizedEvent | None:
        url = raw.get("url")
        host, path = self._split_url(url)
        if not host:
            return None
        return NormalizedEvent(
            occurred_at=self._epoch_to_dt(raw.get("timestamp", "")),
            vector="network_telemetry",
            source="squid",
            domain=host,
            url_path=path,
            user_email=raw.get("user") or raw.get("rfc931"),
            source_ip=raw.get("remote_ip") or raw.get("clientip"),
            bytes_recv=self._safe_int(raw.get("bytes")),
            raw_meta={k: raw[k] for k in ("method", "code_status") if k in raw},
        )

    @staticmethod
    def _epoch_to_dt(s: Any) -> datetime:
        try:
            return datetime.fromtimestamp(float(s), tz=timezone.utc)
        except (TypeError, ValueError):
            return datetime.now(timezone.utc)
