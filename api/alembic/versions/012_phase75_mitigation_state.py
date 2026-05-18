"""Phase 7.5 — Mitigation push state + verification schedule.

Adds to mitigation_actions:
  - vendor_ref          short opaque adapter-emitted ID (no PII)
  - state_blob          JSONB carrying anything the adapter needs for
                        verify()/rollback() — never credentials, never PII
  - verification_due_at next time the verification loop should re-check;
                        NULL when verification is not scheduled

Revision ID: 012_phase75_mitigation_state
Revises: 011_phase74_mitigations
Create Date: 2026-05-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "012_phase75_mitigation_state"
down_revision: Union[str, None] = "011_phase74_mitigations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mitigation_actions",
                  sa.Column("vendor_ref", sa.String(120), nullable=True))
    op.add_column("mitigation_actions",
                  sa.Column("state_blob",
                            postgresql.JSONB(astext_type=sa.Text()),
                            nullable=False,
                            server_default=sa.text("'{}'::jsonb")))
    op.add_column("mitigation_actions",
                  sa.Column("verification_due_at",
                            sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_mitigation_actions_verification_due",
                    "mitigation_actions", ["verification_due_at"])


def downgrade() -> None:
    op.drop_index("ix_mitigation_actions_verification_due",
                  table_name="mitigation_actions")
    op.drop_column("mitigation_actions", "verification_due_at")
    op.drop_column("mitigation_actions", "state_blob")
    op.drop_column("mitigation_actions", "vendor_ref")
