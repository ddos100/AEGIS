"""Phase 7.6 (v0.2.0 agent) — extended EA event kinds.

The agent's process + network monitors emit three new event kinds:

  ai_process_running           AI binary launched on the endpoint
  ai_provider_connection       process opened TCP to an AI provider
                                domain (api.openai.com, api.cursor.sh,
                                api.anthropic.com, ...)
  destructive_cmd_correlation  destructive shell command observed
                                while an AI binary was also active

This migration relaxes the kind CHECK constraint on
endpoint_agent_events to permit the three new values; existing rows
remain valid (the previous values are kept in place).

Revision ID: 015_phase76_ea_more_kinds
Revises:    014_phase76_endpoint_agent
Create Date: 2026-05-19
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "015_phase76_ea_more_kinds"
down_revision: Union[str, None] = "014_phase76_endpoint_agent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE endpoint_agent_events "
        "DROP CONSTRAINT IF EXISTS ck_endpoint_agent_events_kind"
    )
    op.execute(
        """
        ALTER TABLE endpoint_agent_events
        ADD CONSTRAINT ck_endpoint_agent_events_kind
        CHECK (kind IN (
            'process_exec',
            'file_write_to_watched_path',
            'secret_read_by_ai_proc',
            'curl_pipe_sh_detected',
            'mcp_config_observed',
            'package_install_pre_hook',
            'path_shadow_detected',
            'autostart_artifact',
            'heartbeat',
            'ai_process_running',
            'ai_provider_connection',
            'destructive_cmd_correlation'
        ))
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE endpoint_agent_events "
        "DROP CONSTRAINT IF EXISTS ck_endpoint_agent_events_kind"
    )
    op.execute(
        """
        ALTER TABLE endpoint_agent_events
        ADD CONSTRAINT ck_endpoint_agent_events_kind
        CHECK (kind IN (
            'process_exec',
            'file_write_to_watched_path',
            'secret_read_by_ai_proc',
            'curl_pipe_sh_detected',
            'mcp_config_observed',
            'package_install_pre_hook',
            'path_shadow_detected',
            'autostart_artifact',
            'heartbeat'
        ))
        """
    )
