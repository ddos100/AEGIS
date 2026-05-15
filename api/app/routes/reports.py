"""Reports endpoints — generate + list + download executive / framework PDFs."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import desc, select

from app.core.deps import CurrentUser, DBSession, require_admin, require_analyst
from app.models.compliance_framework import ComplianceFramework
from app.models.report import Report
from app.schemas.compliance import ReportBrief, ReportGenerateRequest
from app.services.report_generator import (
    generate_executive_report,
    generate_framework_audit,
)

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("", response_model=list[ReportBrief])
async def list_reports(db: DBSession, user: CurrentUser):  # noqa: ARG001
    rows = (await db.execute(
        select(Report).order_by(desc(Report.requested_at)).limit(50)
    )).scalars().all()
    return [ReportBrief.model_validate(r) for r in rows]


@router.post("/generate", response_model=ReportBrief, status_code=status.HTTP_201_CREATED)
async def generate(
    payload: ReportGenerateRequest,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_analyst)],
) -> ReportBrief:
    report = Report(
        tenant_id=user.tenant_id,
        report_type=payload.report_type,
        framework_id=payload.framework_id,
        parameters=payload.parameters,
        file_format=payload.file_format,
        status="generating",
    )
    db.add(report)
    await db.flush()

    try:
        if payload.report_type == "executive_summary":
            result = await generate_executive_report(
                session=db, tenant_id=user.tenant_id,
                parameters=payload.parameters, file_format=payload.file_format,
            )
        elif payload.report_type == "framework_audit":
            if not payload.framework_id:
                raise HTTPException(status_code=400, detail="framework_id required for framework_audit")
            fw = (await db.execute(
                select(ComplianceFramework).where(ComplianceFramework.id == payload.framework_id)
            )).scalar_one_or_none()
            if fw is None:
                raise HTTPException(status_code=404, detail="Framework not found")
            result = await generate_framework_audit(
                session=db, tenant_id=user.tenant_id, framework_slug=fw.slug,
                file_format=payload.file_format,
            )
        else:
            raise HTTPException(status_code=400,
                                detail=f"Unknown report_type: {payload.report_type}")

        if not result.get("ok"):
            report.status = "failed"
            report.error = result.get("error")
        else:
            report.status = "ready"
            report.file_path = result["file_path"]
            report.file_format = result["file_format"]
            report.file_size_bytes = result["file_size_bytes"]
            report.completed_at = datetime.now(timezone.utc)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        report.status = "failed"
        report.error = str(exc)
    await db.flush()
    await db.refresh(report)
    return ReportBrief.model_validate(report)


@router.get("/{report_id}/download")
async def download(
    report_id: UUID,
    db: DBSession,
    user: CurrentUser,  # noqa: ARG001
):
    row = (await db.execute(select(Report).where(Report.id == report_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if row.status != "ready" or not row.file_path:
        raise HTTPException(status_code=409, detail=f"Report not ready (status={row.status})")
    path = Path(row.file_path)
    if not path.exists():
        raise HTTPException(status_code=410, detail="Report file no longer on disk")
    mime = "application/pdf" if row.file_format == "pdf" else "text/html"
    fname = f"aegis-{row.report_type}-{row.id}.{row.file_format}"
    return FileResponse(str(path), media_type=mime, filename=fname)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: UUID,
    db: DBSession,
    user: Annotated[CurrentUser, Depends(require_admin)],  # noqa: ARG001
) -> None:
    row = (await db.execute(select(Report).where(Report.id == report_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if row.file_path:
        Path(row.file_path).unlink(missing_ok=True)
    await db.delete(row)
