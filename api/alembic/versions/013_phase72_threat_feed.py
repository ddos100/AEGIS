"""Phase 7.2 — Threat-feed ingest + admin review queue.

Adds:
  - raw_threat_feed     append-only log of every record ingested from an
                        upstream source. Indexed by source + ingested_at;
                        retention policy applied separately.
  - draft_threats       per-source normaliser output awaiting admin
                        review. Status: pending_review | published |
                        rejected | superseded. Approved drafts are
                        upserted into the canonical `threats` table
                        and the YAML file is written at the same time
                        (the YAML is the source of truth; the table is
                        the queryable projection).

These tables are GLOBAL (admin-maintained, no tenant_id). Drafts carry
the per-source fingerprint so re-ingest is idempotent.

Revision ID: 013_phase72_threat_feed
Revises: 012_phase75_mitigation_state
Create Date: 2026-05-18
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "013_phase72_threat_feed"
down_revision: Union[str, None] = "012_phase75_mitigation_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============ raw_threat_feed ============
    op.create_table(
        "raw_threat_feed",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("source", sa.String(48), nullable=False,
                  comment="mitre_atlas | osv | aiid | owasp_llm | "
                          "huggingface | pypi | cert_in | sclllp_research"),
        sa.Column("upstream_id", sa.String(255), nullable=False,
                  comment="Source-specific stable identifier, e.g. "
                          "AML.T0051 / GHSA-xxxx / AIID-1234"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("source", "payload_sha256", name="uq_raw_threat_feed_dedup"),
    )
    op.create_index("ix_raw_threat_feed_source_ingested",
                    "raw_threat_feed", ["source", "ingested_at"])

    # ============ draft_threats ============
    op.create_table(
        "draft_threats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("source", sa.String(48), nullable=False),
        sa.Column("upstream_id", sa.String(255), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False,
                  comment="sha256(source|upstream_id) — stable across re-ingest"),
        sa.Column("draft", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                  comment="Candidate threat record matching catalogue/threats/schema.yaml"),
        sa.Column("review_status", sa.String(24), nullable=False, server_default="pending_review",
                  comment="pending_review | published | rejected | superseded"),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_by",  postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at",  sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_threat_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("threats.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ingested_at",  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("created_at",   sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at",   sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint(
            "review_status IN ('pending_review','published','rejected','superseded')",
            name="ck_draft_threats_status",
        ),
        sa.UniqueConstraint("source_fingerprint", name="uq_draft_threats_fingerprint"),
    )
    op.execute(
        "CREATE TRIGGER tg_draft_threats_updated_at BEFORE UPDATE ON draft_threats "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )
    op.create_index("ix_draft_threats_status",
                    "draft_threats", ["review_status", "ingested_at"])


def downgrade() -> None:
    op.drop_table("draft_threats")
    op.drop_table("raw_threat_feed")
