"""Catalogue-pattern matcher built on Aho-Corasick.

At worker startup we load every ``api_pattern`` and ``browser_domain`` from
:class:`app.models.ai_service.AIService` and build a single Aho-Corasick
automaton. The matcher then takes a ``NormalizedEvent``, runs its
``matchable_string`` through the automaton, and returns the best matching
``AIService`` (if any).

Performance: O(n) in the input length, independent of the number of patterns
— matching ~5,000 patterns against a 200-character event is sub-5ms in
practice. The automaton is built once per process and cached on the module.

The matcher is thread-safe for reads (automaton lookups are pure). Rebuilding
must serialise via :data:`_REBUILD_LOCK`.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Iterable

import ahocorasick

from app.integrations.network.base import NormalizedEvent


@dataclass(frozen=True, slots=True)
class CataloguePattern:
    catalogue_id: int                 # internal numeric id (lookup is dict-keyed by it)
    service_id: str                   # AIService.id (UUID stringified)
    catalogue_slug: str               # human-readable id
    name: str
    category: str
    pattern: str                      # the literal that matched
    pattern_kind: str                 # "api" | "browser" | "process"


@dataclass(slots=True)
class MatchResult:
    pattern: CataloguePattern
    matched_string: str


# Internal state -------------------------------------------------------------

_AUTOMATON: ahocorasick.Automaton | None = None
_PROCESS_INDEX: dict[str, CataloguePattern] = {}
_REBUILD_LOCK = threading.Lock()


def _make_pattern(idx: int, *, service_id: str, slug: str, name: str, category: str,
                  pat: str, kind: str) -> CataloguePattern:
    return CataloguePattern(
        catalogue_id=idx,
        service_id=service_id,
        catalogue_slug=slug,
        name=name,
        category=category,
        pattern=pat.lower(),
        pattern_kind=kind,
    )


def build_automaton(services: Iterable[dict]) -> None:
    """(Re)build the global automaton from an iterable of AIService rows.

    Each service dict must have keys: id, catalogue_id, name, category,
    api_patterns (list[str]), browser_domains (list[str]),
    catalogue_meta.process_names (list[str], optional).
    """
    global _AUTOMATON, _PROCESS_INDEX
    automaton = ahocorasick.Automaton()
    process_index: dict[str, CataloguePattern] = {}
    idx = 0
    for svc in services:
        sid = str(svc["id"])
        slug = svc["catalogue_id"]
        name = svc["name"]
        category = svc["category"]
        for pat in svc.get("api_patterns") or []:
            p = _make_pattern(idx, service_id=sid, slug=slug, name=name, category=category,
                              pat=pat, kind="api")
            automaton.add_word(p.pattern, p)
            idx += 1
        for dom in svc.get("browser_domains") or []:
            p = _make_pattern(idx, service_id=sid, slug=slug, name=name, category=category,
                              pat=dom, kind="browser")
            automaton.add_word(p.pattern, p)
            idx += 1
        # Process name index (exact match, separate from substring automaton).
        meta = svc.get("catalogue_meta") or {}
        for proc in meta.get("process_names") or []:
            p = _make_pattern(idx, service_id=sid, slug=slug, name=name, category=category,
                              pat=proc, kind="process")
            process_index[proc.lower()] = p
            idx += 1
    if len(automaton) > 0:
        automaton.make_automaton()
    with _REBUILD_LOCK:
        _AUTOMATON = automaton
        _PROCESS_INDEX = process_index


def _need_automaton() -> ahocorasick.Automaton:
    if _AUTOMATON is None:
        raise RuntimeError(
            "Catalogue matcher not initialised. Call build_automaton(...) at worker startup."
        )
    return _AUTOMATON


def match_event(event: NormalizedEvent) -> MatchResult | None:
    """Find the most specific catalogue pattern matching this event.

    Strategy:
      1. If the event has a process_name, look it up in the exact-match index
         first (deterministic match for desktop AI agents like 'ChatGPT.exe').
      2. Otherwise run the matchable_string (domain[+path]) through the
         Aho-Corasick automaton and pick the longest hit (most-specific wins).
    """
    if event.process_name:
        hit = _PROCESS_INDEX.get(event.process_name.lower())
        if hit:
            return MatchResult(pattern=hit, matched_string=event.process_name.lower())

    s = event.matchable_string.lower()
    if not s:
        return None
    automaton = _need_automaton()
    best: MatchResult | None = None
    for _, pat in automaton.iter(s):
        if best is None or len(pat.pattern) > len(best.pattern.pattern):
            best = MatchResult(pattern=pat, matched_string=pat.pattern)
    return best


def matcher_size() -> dict[str, int]:
    automaton = _AUTOMATON
    return {
        "ac_patterns": len(automaton) if automaton is not None else 0,
        "process_patterns": len(_PROCESS_INDEX),
    }


# Convenience loader used by both API + worker startup ----------------------

async def load_from_db() -> int:
    """Load every active AIService row from the DB and (re)build the automaton.

    Returns the number of services indexed. Safe to call repeatedly; each call
    completely replaces the prior automaton.
    """
    from sqlalchemy import select
    from app.core.database import engine
    from app.models.ai_service import AIService

    async with engine.connect() as conn:
        result = await conn.execute(
            select(
                AIService.id, AIService.catalogue_id, AIService.name,
                AIService.category, AIService.api_patterns, AIService.browser_domains,
            ).where(AIService.is_active.is_(True))
        )
        rows = result.mappings().all()

    build_automaton([dict(r) for r in rows])
    return len(rows)
