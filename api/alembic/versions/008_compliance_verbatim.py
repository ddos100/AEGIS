"""Phase 6 — Compliance verbatim requirements + source references.

Adds two columns to compliance_controls so the platform can reproduce the
**exact** regulatory requirement that applies to AI for each control:

  - requirement_text   The verbatim (or near-verbatim) regulatory clause.
                       This is what the auditor sees; it must not be
                       paraphrased.
  - source_ref         The authoritative citation — e.g. "ISO/IEC 42001:2023
                       Annex A.4.3", "EU AI Act Art. 11(1)", "DPDPA 2023
                       s. 7(a)" — so a reader can verify the wording against
                       the source document.

Both fields are nullable to preserve backwards compatibility with the rows
already imported by migration 007; the YAML importer fills them on the next
`make framework-import` pass.

Revision ID: 008_compliance_verbatim
Revises: 007_phase5_compliance
Create Date: 2026-05-16
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_compliance_verbatim"
down_revision: Union[str, None] = "007_phase5_compliance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "compliance_controls",
        sa.Column("requirement_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "compliance_controls",
        sa.Column("source_ref", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("compliance_controls", "source_ref")
    op.drop_column("compliance_controls", "requirement_text")
