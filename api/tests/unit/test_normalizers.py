"""Unit tests for every concrete normalizer.

Each test feeds a small representative real-world record into the parser and
asserts the canonical fields land where they should. These are pure-Python
tests — no DB, no Redis. They run in < 1s.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

# Ensure decorators fire before we look up normalizers.
from app.integrations.network.base import get_normalizer, load_all_normalizers, registered_sources

load_all_normalizers()


# ---------- Zscaler ----------

def test_zscaler_nss_native_json() -> None:
    raw = {
        "user": "alice@example.com",
        "department": "Finance",
        "url": "https://chat.openai.com/v1/chat/completions",
        "host": "chat.openai.com",
        "cip": "10.0.1.5",
        "time": 1715600000,
        "reqsize": 1234, "respsize": 4567,
        "action": "allow",
    }
    ev = get_normalizer("zscaler_nss").parse(raw)
    assert ev is not None
    assert ev.domain == "chat.openai.com"
    assert ev.url_path == "/v1/chat/completions"
    assert ev.user_email == "alice@example.com"
    assert ev.department == "Finance"
    assert ev.source_ip == "10.0.1.5"
    assert ev.bytes_sent == 1234
    assert ev.bytes_recv == 4567
    assert ev.vector == "network_telemetry"


def test_zscaler_drops_records_without_url() -> None:
    assert get_normalizer("zscaler_nss").parse({"user": "a"}) is None
    assert get_normalizer("zscaler_nss").parse("not a dict") is None


# ---------- Squid ----------

def test_squid_native_log_line() -> None:
    line = ("1715600000.123 184 10.0.1.5 TCP_TUNNEL/200 53412 CONNECT "
            "chat.openai.com:443 alice HIER_DIRECT/104.18.32.7 -")
    ev = get_normalizer("squid").parse(line)
    assert ev is not None
    assert ev.domain == "chat.openai.com"
    assert ev.user_email == "alice"
    assert ev.source_ip == "10.0.1.5"
    assert ev.bytes_recv == 53412


def test_squid_dict_payload() -> None:
    ev = get_normalizer("squid").parse({
        "timestamp": 1715600000,
        "url": "https://claude.ai/login",
        "user": "bob@example.com",
        "remote_ip": "10.0.1.6",
        "bytes": 8192,
    })
    assert ev is not None
    assert ev.domain == "claude.ai"
    assert ev.url_path == "/login"
    assert ev.user_email == "bob@example.com"


# ---------- OCSF ----------

def test_ocsf_http_activity() -> None:
    raw = {
        "class_uid": 4002,
        "time": 1715600000000,  # ms
        "http_request": {"url": {"url_string": "https://gemini.google.com/app"}},
        "actor": {"user": {"email_addr": "carol@example.com", "org": {"name": "Eng"}}},
        "src_endpoint": {"ip": "10.0.1.7", "hostname": "carol-laptop"},
        "traffic": {"bytes_in": 2048, "bytes_out": 512},
    }
    ev = get_normalizer("ocsf").parse(raw)
    assert ev is not None
    assert ev.domain == "gemini.google.com"
    assert ev.url_path == "/app"
    assert ev.user_email == "carol@example.com"
    assert ev.department == "Eng"
    assert ev.bytes_sent == 512
    assert ev.bytes_recv == 2048


def test_ocsf_process_activity_marked_as_xdr() -> None:
    raw = {
        "class_uid": 1001,
        "time": "2026-05-13T08:30:00Z",
        "process": {"name": "ChatGPT.exe", "cmd_line": "ChatGPT.exe"},
        "actor": {"user": {"email_addr": "dave@example.com"}},
        "device": {"hostname": "WIN-DAVE"},
    }
    ev = get_normalizer("ocsf").parse(raw)
    assert ev is not None
    assert ev.vector == "xdr_edr"
    assert ev.process_name == "ChatGPT.exe"
    assert ev.user_email == "dave@example.com"
    assert ev.hostname == "WIN-DAVE"


# ---------- CEF ----------

def test_cef_fortinet_line() -> None:
    line = ('CEF:0|Fortinet|FortiGate|7.4.0|13|allowed|3|'
            'src=10.0.1.5 dst=104.18.32.7 request=https://chat.openai.com/v1/chat '
            'suser=alice@example.com out=2348 in=128 rt=1715600000000')
    ev = get_normalizer("cef").parse(line)
    assert ev is not None
    assert ev.domain == "chat.openai.com"
    assert ev.url_path == "/v1/chat"
    assert ev.user_email == "alice@example.com"
    assert ev.source_ip == "10.0.1.5"
    assert ev.bytes_sent == 2348
    assert ev.bytes_recv == 128


def test_cef_falcon_marked_as_xdr() -> None:
    line = ('CEF:0|CrowdStrike|Falcon|6.0|DnsRequest|info|2|'
            'dhost=api.anthropic.com sproc=Claude.app shost=mac-eve suser=eve@example.com rt=1715600000000')
    ev = get_normalizer("cef").parse(line)
    assert ev is not None
    assert ev.vector == "xdr_edr"


# ---------- CrowdStrike streaming ----------

def test_crowdstrike_dns_request() -> None:
    raw = {
        "metadata": {"eventType": "DnsRequest", "eventCreationTime": 1715600000000},
        "event": {
            "DomainName": "api.openai.com",
            "ContextTimeStamp": 1715600000,
            "UserName": "alice",
            "ComputerName": "WIN-ALICE",
            "ImageFileName": "chrome.exe",
        },
    }
    ev = get_normalizer("crowdstrike").parse(raw)
    assert ev is not None
    assert ev.domain == "api.openai.com"
    assert ev.vector == "xdr_edr"
    assert ev.process_name == "chrome.exe"


def test_crowdstrike_process_rollup() -> None:
    raw = {"metadata": {"eventType": "ProcessRollup2"},
           "event": {"ImageFileName": "ChatGPT.exe", "ContextTimeStamp": 1715600000,
                     "UserName": "alice", "ComputerName": "WIN-ALICE",
                     "SHA256HashData": "abc123"}}
    ev = get_normalizer("crowdstrike").parse(raw)
    assert ev is not None
    assert ev.process_name == "ChatGPT.exe"
    assert ev.process_hash == "abc123"


# ---------- SentinelOne ----------

def test_sentinelone_dns_action() -> None:
    raw = {
        "eventType": "DNSAction",
        "eventTime": "2026-05-13T08:30:00Z",
        "dnsRequest": "claude.ai",
        "loginUser": "alice",
        "endpointName": "MAC-ALICE",
        "srcProcName": "Claude.app",
    }
    ev = get_normalizer("sentinelone").parse(raw)
    assert ev is not None
    assert ev.domain == "claude.ai"
    assert ev.vector == "xdr_edr"
    assert ev.process_name == "Claude.app"


# ---------- Palo Alto ----------

def test_paloalto_url_log() -> None:
    raw = {
        "time_generated": "2026/05/13 08:30:00",
        "src_user": "alice@example.com",
        "src_ip": "10.0.1.5",
        "url": "chat.openai.com/v1/chat",
        "bytes_sent": "1500",
        "bytes_received": "8000",
        "app": "openai",
        "action": "allow",
    }
    ev = get_normalizer("paloalto").parse(raw)
    assert ev is not None
    assert ev.domain == "chat.openai.com"
    assert ev.user_email == "alice@example.com"
    assert ev.bytes_sent == 1500


# ---------- Cisco Umbrella ----------

def test_cisco_umbrella_dns() -> None:
    raw = {
        "timestamp": "2026-05-13 08:30:00",
        "domain": "api.anthropic.com.",
        "identities": "alice@example.com",
        "internal_ip": "10.0.1.5",
        "action": "allowed",
    }
    ev = get_normalizer("cisco_umbrella").parse(raw)
    assert ev is not None
    assert ev.domain == "api.anthropic.com"          # trailing dot stripped
    assert ev.user_email == "alice@example.com"


# ---------- Cloudflare Gateway ----------

def test_cloudflare_gateway_dns() -> None:
    raw = {
        "EventTimestamp": "2026-05-13T08:30:00Z",
        "UserEmail": "alice@example.com",
        "QueryName": "chat.openai.com.",
        "Action": "allow",
        "DeviceID": "dev-1",
    }
    ev = get_normalizer("cloudflare_gateway").parse(raw)
    assert ev is not None
    assert ev.domain == "chat.openai.com"
    assert ev.user_email == "alice@example.com"


# ---------- Registry sanity ----------

def test_every_source_is_registered() -> None:
    sources = registered_sources()
    for expected in ("zscaler_nss", "squid", "ocsf", "cef", "crowdstrike",
                     "sentinelone", "paloalto", "cisco_umbrella", "cloudflare_gateway"):
        assert expected in sources, f"missing normalizer registration for {expected}"


def test_unknown_source_raises() -> None:
    from app.integrations.network.base import get_normalizer as gn
    with pytest.raises(KeyError):
        gn("bogus_vendor")
