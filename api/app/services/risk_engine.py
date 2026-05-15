"""5-dimension risk scoring engine.

  Data Sensitivity     30%   max class of data_types_processed
  AI Capability        20%   strongest capability across system + catalogue
  Regulatory Exposure  20%   max of regulatory-flag rubric
  Access Scope         15%   user_population estimate
  Provider Trust       15%   100 - catalogue.provider_trust_score

Total is a weighted sum 0–100 mapped to four tiers:

  Critical : 75–100
  High     : 50–74
  Medium   : 25–49
  Low      :  0–24

Recalculated daily by Celery beat for every AISystem. Individual systems can be
re-scored on demand via POST /v1/risk/systems/{id}/assess.

This module is pure-Python — the test suite can exercise every dimension
deterministically without a DB.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

DIMENSION_WEIGHTS: dict[str, float] = {
    "data_sensitivity":    0.30,
    "ai_capability":       0.20,
    "regulatory_exposure": 0.20,
    "access_scope":        0.15,
    "provider_trust":      0.15,
}

# ---------- rubrics ----------

DATA_SENSITIVITY_RUBRIC: dict[str, int] = {
    "biometric":          100,
    "health":              90,
    "sensitive_personal":  80,
    "credentials":         80,
    "financial":           70,
    "intellectual_property": 70,
    "personal":            50,
    "internal":            30,
    "public":              10,
    "other":               40,
}

CAPABILITY_RUBRIC: dict[str, int] = {
    "autonomous_agent":   100,
    "decision_making":     90,
    "code_generation":     80,
    "function_calling":    70,
    "recommendation":      60,
    "text_generation":     50,
    "image_generation":    50,
    "video_generation":    55,
    "vision":              50,
    "speech_to_text":      40,
    "text_to_speech":      40,
    "summarization":       40,
    "classification":      40,
    "embedding":           20,
    "browser_automation":  85,
}

REGULATORY_RUBRIC: dict[str, int] = {
    "eu_ai_act_unacceptable": 100,
    "eu_ai_act_high_risk":     90,
    "dpdpa_applicable":        80,
    "rbi_regulated":           90,
    "irdai_regulated":         85,
    "sebi_regulated":          85,
    "iso42001_scope":          40,
    "general_purpose_ai":      40,
    "limited_risk":            20,
    "minimal_risk":            10,
    "no_regulation":           10,
}

ACCESS_SCOPE_RUBRIC: dict[str, int] = {
    "public":            100,
    "customers":          90,
    "all_employees":     100,
    "large_department":   70,
    "department":         60,
    "team":               40,
    "team_only":          40,
    "single_user":        10,
}

RISK_BANDS = (
    ("critical", 75),
    ("high",     50),
    ("medium",   25),
    ("low",       0),
)


@dataclass(slots=True)
class RiskScore:
    data_sensitivity:    int
    ai_capability:       int
    regulatory_exposure: int
    access_scope:        int
    provider_trust:      int
    total: int
    risk_level: str
    inputs: dict[str, Any]

    @property
    def needs_narrative(self) -> bool:
        return self.risk_level in ("critical", "high")


# ---------- public API ----------

def compute_risk_score(
    system: Mapping[str, Any],
    *,
    catalogue: Mapping[str, Any] | None = None,
) -> RiskScore:
    """Score a single AI system.

    ``system`` is a dict with the canonical AISystem fields. ``catalogue`` is
    the linked AIService dict (if any) — used to derive capability + provider
    trust hints.
    """
    inputs: dict[str, Any] = {}

    data_score    = _score_data_sensitivity(system, inputs)
    capability    = _score_capability(system, catalogue, inputs)
    regulatory    = _score_regulatory(system, inputs)
    access        = _score_access(system, inputs)
    provider      = _score_provider_trust(catalogue, inputs)

    total = round(
        data_score   * DIMENSION_WEIGHTS["data_sensitivity"] +
        capability   * DIMENSION_WEIGHTS["ai_capability"] +
        regulatory   * DIMENSION_WEIGHTS["regulatory_exposure"] +
        access       * DIMENSION_WEIGHTS["access_scope"] +
        provider     * DIMENSION_WEIGHTS["provider_trust"]
    )
    total = max(0, min(100, total))
    level = _band(total)

    return RiskScore(
        data_sensitivity=data_score,
        ai_capability=capability,
        regulatory_exposure=regulatory,
        access_scope=access,
        provider_trust=provider,
        total=total,
        risk_level=level,
        inputs=inputs,
    )


def _band(score: int) -> str:
    for label, threshold in RISK_BANDS:
        if score >= threshold:
            return label
    return "low"


# ---------- dimension scorers ----------

def _score_data_sensitivity(system: Mapping[str, Any], inputs: dict[str, Any]) -> int:
    data_types = system.get("data_types_processed") or []
    if not data_types:
        inputs["data_types_processed"] = []
        return 0
    score = max(DATA_SENSITIVITY_RUBRIC.get(d, 0) for d in data_types)
    inputs["data_types_processed"] = list(data_types)
    inputs["data_score_basis"] = max(data_types, key=lambda d: DATA_SENSITIVITY_RUBRIC.get(d, 0))
    return score


def _score_capability(system: Mapping[str, Any], catalogue: Mapping[str, Any] | None,
                      inputs: dict[str, Any]) -> int:
    caps: list[str] = []
    if catalogue:
        caps.extend(catalogue.get("capabilities") or [])
    # System-level hint from the category (LLM/agent/code etc.)
    cat = system.get("category")
    cat_caps = {
        "llm":         ["text_generation"],
        "code":        ["code_generation"],
        "image_gen":   ["image_generation"],
        "video_gen":   ["video_generation"],
        "speech":      ["text_to_speech"],
        "embedding":   ["embedding"],
        "agent":       ["autonomous_agent"],
        "classifier":  ["classification"],
        "recommendation": ["recommendation"],
        "browser_extension": ["browser_automation"],
    }.get(cat or "", [])
    caps.extend(cat_caps)

    if not caps:
        return 0
    score = max(CAPABILITY_RUBRIC.get(c, 0) for c in caps)
    inputs["capabilities_considered"] = sorted(set(caps))
    return score


def _score_regulatory(system: Mapping[str, Any], inputs: dict[str, Any]) -> int:
    flags = []
    cf = system.get("compliance_flags") or {}
    if cf.get("rbi"):     flags.append("rbi_regulated")
    if cf.get("irdai"):   flags.append("irdai_regulated")
    if cf.get("sebi"):    flags.append("sebi_regulated")
    if cf.get("dpdpa"):   flags.append("dpdpa_applicable")
    if cf.get("iso42001"):flags.append("iso42001_scope")

    # EU AI Act mapping
    eu_cat = system.get("eu_ai_act_category")
    if eu_cat:
        flags.append({
            "unacceptable":         "eu_ai_act_unacceptable",
            "high_risk":            "eu_ai_act_high_risk",
            "limited_risk":         "limited_risk",
            "minimal_risk":         "minimal_risk",
            "general_purpose_ai":   "general_purpose_ai",
        }.get(eu_cat, "no_regulation"))

    # India-sector heuristic — if data is personal + tenant tagged finance / health
    data_types = set(system.get("data_types_processed") or [])
    if "financial" in data_types and "rbi_regulated" not in flags:
        flags.append("rbi_regulated")
    if "health" in data_types and "irdai_regulated" not in flags:
        flags.append("irdai_regulated")
    if "personal" in data_types or "sensitive_personal" in data_types:
        if "dpdpa_applicable" not in flags:
            flags.append("dpdpa_applicable")

    if not flags:
        return REGULATORY_RUBRIC["no_regulation"]
    score = max(REGULATORY_RUBRIC.get(f, 0) for f in flags)
    inputs["regulatory_flags"] = sorted(set(flags))
    return score


def _score_access(system: Mapping[str, Any], inputs: dict[str, Any]) -> int:
    pop = (system.get("user_population") or "").lower()
    subjects = set(system.get("affected_data_subjects") or [])
    candidates: list[str] = []
    if not pop and not subjects:
        return 0
    if "public" in subjects:
        candidates.append("public")
    if "customers" in subjects:
        candidates.append("customers")
    # rough heuristics on user_population free-text
    if "all" in pop or "organisation-wide" in pop or "company" in pop:
        candidates.append("all_employees")
    elif "department" in pop:
        candidates.append("large_department" if "large" in pop else "department")
    elif "team" in pop or "squad" in pop:
        candidates.append("team_only")
    elif "single" in pop or "one user" in pop or "individual" in pop:
        candidates.append("single_user")

    if not candidates:
        candidates.append("team_only")
    score = max(ACCESS_SCOPE_RUBRIC.get(c, 0) for c in candidates)
    inputs["access_scope_basis"] = candidates
    return score


def _score_provider_trust(catalogue: Mapping[str, Any] | None,
                          inputs: dict[str, Any]) -> int:
    if not catalogue:
        return 60        # unknown provider → moderate-high risk
    hints = catalogue.get("risk_hints") or {}
    trust = hints.get("provider_trust_score")
    if trust is None:
        return 60
    inputs["provider_trust_raw"] = trust
    return max(0, min(100, 100 - int(trust)))
