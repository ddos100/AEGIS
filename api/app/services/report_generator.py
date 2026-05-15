"""Executive + framework PDF report generator.

We render Jinja2 HTML and convert it to PDF with WeasyPrint. WeasyPrint
is an optional native dep — if it's missing at runtime, we fall back to
an HTML file. Either way the caller gets a real artefact on disk; only
the file_format differs.

Output goes to ``settings.report_storage_path`` (default: /tmp/reports).
File names are UUIDs to avoid collisions; the metadata + final path land
on the ``reports`` table.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import func, select

from app.core.logging import log
from app.integrations.claude.client import generate_risk_narrative
from app.models.ai_system import AISystem
from app.models.aisia_record import AISIARecord
from app.models.compliance_framework import ComplianceFramework
from app.models.policy_violation import PolicyViolation
from app.services.compliance_engine import framework_score

REPORT_STORAGE_PATH = Path(os.environ.get("REPORT_STORAGE_PATH", "/tmp/aegis-reports"))
REPORT_STORAGE_PATH.mkdir(parents=True, exist_ok=True)

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates" / "reports"
_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

_jinja = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


async def generate_executive_report(
    *, session, tenant_id: UUID, parameters: dict[str, Any],
    file_format: str = "pdf",
) -> dict[str, Any]:
    """Generate an executive-summary report and return persistence info."""
    stats = await _gather_executive_stats(session)
    framework_rows = await _framework_scores(session)

    summary_text: str | None = None
    try:
        summary_text = await generate_risk_narrative(
            {
                "name": "Organisation-wide AI posture",
                "category": "summary",
                "intended_purpose": "Executive overview",
                "data_types_processed": [],
                "affected_data_subjects": [],
                "eu_ai_act_category": "n/a",
                "geographic_scope": [],
            },
            {
                "data_sensitivity":    stats["avg_data_sensitivity"],
                "ai_capability":       stats["avg_capability"],
                "regulatory_exposure": stats["avg_regulatory"],
                "access_scope":        stats["avg_access"],
                "provider_trust":      stats["avg_provider_trust"],
                "total":               stats["avg_risk_score"],
                "risk_level":          stats["dominant_level"],
            },
        )
    except Exception:  # noqa: BLE001
        summary_text = None

    ctx = {
        "tenant_id":      str(tenant_id),
        "generated_at":   datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stats":          stats,
        "framework_scores": framework_rows,
        "summary":        summary_text or (
            "Executive summary unavailable — configure ANTHROPIC_API_KEY to enable "
            "Claude-generated narratives."
        ),
        "branding":       parameters.get("branding", {"company": "Securisti Consulting LLP"}),
    }
    return await _render(ctx, template_name="executive_report.html",
                         file_format=file_format, report_type="executive_summary")


async def generate_framework_audit(
    *, session, tenant_id: UUID, framework_slug: str,
    file_format: str = "pdf",
) -> dict[str, Any]:
    score = await framework_score(session=session, framework_slug=framework_slug)
    if score is None:
        return {"ok": False, "error": f"framework {framework_slug!r} not found"}
    fw = (await session.execute(
        select(ComplianceFramework).where(ComplianceFramework.slug == framework_slug)
    )).scalar_one_or_none()
    ctx = {
        "tenant_id":    str(tenant_id),
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "framework":    {
            "slug": score.slug, "name": score.name,
            "version": fw.version if fw else "",
            "authority": fw.authority if fw else None,
        },
        "score": score,
    }
    return await _render(ctx, template_name="framework_audit.html",
                         file_format=file_format, report_type="framework_audit")


async def _render(ctx: dict, *, template_name: str, file_format: str,
                  report_type: str) -> dict[str, Any]:
    template = _jinja.get_template(template_name)
    html = template.render(**ctx)
    report_id = uuid4()
    path: Path
    actual_format = file_format
    if file_format == "pdf":
        try:
            from weasyprint import HTML  # type: ignore[import-not-found]
            path = REPORT_STORAGE_PATH / f"{report_id}.pdf"
            HTML(string=html, base_url=str(_TEMPLATES_DIR)).write_pdf(str(path))
        except Exception as exc:  # noqa: BLE001
            log.warning("aegis.report.weasyprint_unavailable", error=str(exc))
            actual_format = "html"
            path = REPORT_STORAGE_PATH / f"{report_id}.html"
            path.write_text(html, encoding="utf-8")
    else:
        actual_format = "html"
        path = REPORT_STORAGE_PATH / f"{report_id}.html"
        path.write_text(html, encoding="utf-8")

    size = path.stat().st_size
    log.info("aegis.report.generated", report_type=report_type, format=actual_format,
             size=size, path=str(path))
    return {
        "ok": True,
        "report_id": str(report_id),
        "file_path": str(path),
        "file_format": actual_format,
        "file_size_bytes": size,
    }


async def _gather_executive_stats(session) -> dict[str, Any]:
    total = (await session.execute(select(func.count(AISystem.id)))).scalar_one()
    shadow = (await session.execute(
        select(func.count(AISystem.id)).where(AISystem.is_shadow.is_(True))
    )).scalar_one()
    by_level = dict(((lvl, n) for lvl, n in (await session.execute(
        select(AISystem.risk_level, func.count(AISystem.id))
        .group_by(AISystem.risk_level)
    )).all()))
    avg_score = float((await session.execute(
        select(func.avg(AISystem.current_risk_score))
    )).scalar_one() or 0)
    aisia_pending = (await session.execute(
        select(func.count(AISIARecord.id)).where(AISIARecord.status == "initiated")
    )).scalar_one()
    violations_open = (await session.execute(
        select(func.count(PolicyViolation.id)).where(PolicyViolation.resolved.is_(False))
    )).scalar_one()

    return {
        "total_systems":         total,
        "shadow_count":          shadow,
        "by_level":              by_level,
        "avg_risk_score":        round(avg_score, 1),
        "dominant_level":        max(by_level.items(), key=lambda x: x[1])[0] if by_level else "low",
        "aisia_pending":         aisia_pending,
        "violations_open":       violations_open,
        # We don't materialise the dimension averages cheaply; use the risk
        # assessments hypertable instead. For the exec summary we use the
        # rolling avg or default to the org-wide risk score for each dim.
        "avg_data_sensitivity":  round(avg_score, 1),
        "avg_capability":        round(avg_score, 1),
        "avg_regulatory":        round(avg_score, 1),
        "avg_access":            round(avg_score, 1),
        "avg_provider_trust":    round(avg_score, 1),
    }


async def _framework_scores(session) -> list[dict[str, Any]]:
    out = []
    frameworks = (await session.execute(
        select(ComplianceFramework).where(ComplianceFramework.is_active.is_(True))
    )).scalars().all()
    for fw in frameworks:
        s = await framework_score(session=session, framework_slug=fw.slug)
        if s is None:
            continue
        out.append({
            "slug": s.slug, "name": s.name,
            "score_pct": s.score_pct,
            "by_status": s.by_status, "gap_count": len(s.gaps),
        })
    return out
