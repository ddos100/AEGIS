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
from app.models.ai_service import AIService
from app.models.ai_system import AISystem
from app.models.ai_usage_event import AIUsageEvent
from app.models.discovery_vector import DiscoveryVector
from app.models.extension_device import ExtensionDevice
from app.models.integration_credential import IntegrationCredential
from app.models.idp_user import IdpUser
from app.models.oauth_grant import OAuthGrant
from app.models.cloud_ai_resource import CloudAIResource
from app.models.risk_assessment import RiskAssessment
from app.models.aisia_record import AISIARecord
from app.models.policy import Policy
from app.models.policy_violation import PolicyViolation
from app.models.audit_log import AuditLog

__all__ = [
    "Base", "Tenant", "User", "Department",
    "AIProvider", "AIService", "AISystem", "AIUsageEvent",
    "DiscoveryVector", "ExtensionDevice",
    "IntegrationCredential", "IdpUser", "OAuthGrant", "CloudAIResource",
    "RiskAssessment", "AISIARecord", "Policy", "PolicyViolation",
    "AuditLog",
]
