"""SQLAlchemy ORM models.

All tenant-scoped tables MUST include a ``tenant_id`` column and an RLS policy
defined in the corresponding Alembic migration. The application is expected to
set ``app.current_tenant`` per request via :func:`app.core.database.session_scope`.
"""
from app.models.base import Base
from app.models.tenant import Tenant
from app.models.user import User
from app.models.department import Department
from app.models.ai_provider import AIProvider
from app.models.audit_log import AuditLog

__all__ = ["Base", "Tenant", "User", "Department", "AIProvider", "AuditLog"]
