"""Aho-Corasick matcher unit tests.

Builds an automaton from a small in-memory catalogue and asserts the
match-most-specific behaviour.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.integrations.network.base import NormalizedEvent
from app.integrations.network.matcher import build_automaton, match_event, matcher_size


CATALOGUE = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "catalogue_id": "openai-chatgpt",
        "name": "ChatGPT",
        "category": "llm",
        "api_patterns": ["api.openai.com/v1/chat/completions", "api.openai.com"],
        "browser_domains": ["chat.openai.com", "chatgpt.com"],
        "catalogue_meta": {"process_names": ["ChatGPT.exe"]},
    },
    {
        "id": "22222222-2222-2222-2222-222222222222",
        "catalogue_id": "anthropic-claude",
        "name": "Claude",
        "category": "llm",
        "api_patterns": ["api.anthropic.com"],
        "browser_domains": ["claude.ai"],
    },
]


def _ev(domain: str | None = None, path: str | None = None, process: str | None = None) -> NormalizedEvent:
    return NormalizedEvent(
        occurred_at=datetime.now(timezone.utc),
        vector="network_telemetry",
        source="test",
        domain=domain,
        url_path=path,
        process_name=process,
    )


def setup_module(_module) -> None:
    build_automaton(CATALOGUE)


def test_matcher_size_reports_patterns() -> None:
    size = matcher_size()
    # 2 api + 2 browser + 0 process for ChatGPT  +  1 api + 1 browser for Claude  = 6 AC
    assert size["ac_patterns"] == 6
    assert size["process_patterns"] == 1   # only ChatGPT.exe


def test_match_browser_domain() -> None:
    m = match_event(_ev(domain="chat.openai.com"))
    assert m is not None and m.pattern.catalogue_slug == "openai-chatgpt"


def test_match_api_with_path_picks_most_specific() -> None:
    # Both "api.openai.com" and "api.openai.com/v1/chat/completions" are registered;
    # the longer pattern should win.
    m = match_event(_ev(domain="api.openai.com", path="/v1/chat/completions"))
    assert m is not None and m.matched_string == "api.openai.com/v1/chat/completions"


def test_no_match_returns_none() -> None:
    assert match_event(_ev(domain="random-not-ai.example.com")) is None


def test_process_name_exact_index() -> None:
    m = match_event(_ev(process="ChatGPT.exe"))
    assert m is not None and m.pattern.pattern_kind == "process"
    assert m.pattern.catalogue_slug == "openai-chatgpt"


def test_process_case_insensitive() -> None:
    m = match_event(_ev(process="chatgpt.exe"))
    assert m is not None and m.pattern.catalogue_slug == "openai-chatgpt"


def test_empty_event_returns_none() -> None:
    assert match_event(_ev()) is None
