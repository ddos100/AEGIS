"""AEGIS Endpoint Agent mitigation primitives (Phase 7.5+).

These adapters push policy directives to enrolled AEGIS EA devices.
In real-mode the orchestrator writes a policy record to the
`ea_device_policies` table; the next agent heartbeat pulls the updated
policy and enforces it locally (block / warn / audit).

Unlike vendor adapters these are AEGIS-native — no external API.  The
apply() writes to the AEGIS DB; verify() reads back.  Still dry-run in
v1 so the operator can see the proposed directives before they ship.

Enforcement modes (per directive):
  block — the agent kills the process / refuses the operation
  warn  — the agent logs a high-severity event but allows
  audit — silent observation; event stored for exposure predicate

All 12 primitives map 1:1 to EA detection capabilities.
"""
from __future__ import annotations

from app.integrations.mitigations._drylib import dry_apply, dry_rollback, dry_verify
from app.integrations.mitigations.base import BaseMitigationAdapter, register

_API_LABEL = "AEGIS Endpoint Agent device policy"


# ── 1. curl | sh / wget | sh ────────────────────────────────────────

@register(integration="aegis_endpoint_agent", action="curl_pipe_sh_block")
class EACurlPipeShBlock(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="EA-CPSH",
            required=["enforcement"],
            params=params,
            detail_tmpl="would push EA policy: {enforcement!r} on curl|sh / wget|sh "
                        "pipe-to-shell patterns detected by procmon",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)


# ── 2. Package manager pre-install hook abuse ───────────────────────

@register(integration="aegis_endpoint_agent", action="package_install_pre_hook_block")
class EAPackageInstallPreHookBlock(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="EA-PIHK",
            required=["enforcement"],
            params=params,
            detail_tmpl="would push EA policy: {enforcement!r} on npm/pip/cargo "
                        "pre/post-install hooks executing under AI-spawned processes",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)


# ── 3. Secret path reads by AI processes ─────────────────────────────

@register(integration="aegis_endpoint_agent", action="secret_path_read_block")
class EASecretPathReadBlock(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="EA-SECR",
            required=["enforcement"],
            params=params,
            detail_tmpl="would push EA policy: {enforcement!r} when AI-tree processes "
                        "read files matching secret-path patterns (~/.ssh/*, .env, "
                        "credentials.json, etc.)",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)


# ── 4. MCP config mutation warning ──────────────────────────────────

@register(integration="aegis_endpoint_agent", action="mcp_config_policy_warn")
class EAMCPConfigPolicyWarn(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="EA-MCP",
            required=["enforcement"],
            params=params,
            detail_tmpl="would push EA policy: {enforcement!r} when MCP config files "
                        "(claude_desktop_config.json, .cursor/mcp.json, etc.) are "
                        "written or modified",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)


# ── 5. Destructive commands under AI process tree ────────────────────

@register(integration="aegis_endpoint_agent", action="destructive_cmd_block_under_ai_proc")
class EADestructiveCmdBlock(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="EA-DCMD",
            required=["enforcement"],
            params=params,
            detail_tmpl="would push EA policy: {enforcement!r} on destructive commands "
                        "(rm -rf, format, del /s, mkfs, dd) spawned under AI process "
                        "trees (Claude, Cursor, Copilot, etc.)",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)


# ── 6. git push pre-hook block ───────────────────────────────────────

@register(integration="aegis_endpoint_agent", action="git_push_pre_hook_block")
class EAGitPushPreHookBlock(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="EA-GPSH",
            required=["enforcement"],
            params=params,
            detail_tmpl="would push EA policy: {enforcement!r} when git push is "
                        "executed from an AI-spawned process tree without prior "
                        "human review attestation",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)


# ── 7. docker --privileged under AI process ──────────────────────────

@register(integration="aegis_endpoint_agent", action="docker_privileged_block_under_ai_proc")
class EADockerPrivilegedBlock(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="EA-DPRV",
            required=["enforcement"],
            params=params,
            detail_tmpl="would push EA policy: {enforcement!r} when docker run "
                        "--privileged or --cap-add is invoked from an AI process tree",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)


# ── 8. npm postinstall script block ──────────────────────────────────

@register(integration="aegis_endpoint_agent", action="npm_postinstall_block")
class EANpmPostinstallBlock(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="EA-NPMI",
            required=["enforcement"],
            params=params,
            detail_tmpl="would push EA policy: {enforcement!r} when npm lifecycle "
                        "scripts (preinstall/postinstall) execute network calls or "
                        "spawn shells under AI-initiated installs",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)


# ── 9. Shell RC file writes ──────────────────────────────────────────

@register(integration="aegis_endpoint_agent", action="shell_rc_write_block")
class EAShellRcWriteBlock(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="EA-SHRC",
            required=["enforcement"],
            params=params,
            detail_tmpl="would push EA policy: {enforcement!r} when AI processes "
                        "write to shell RC files (.bashrc, .zshrc, .profile, "
                        "PowerShell profile) for persistence",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)


# ── 10. SUID bit stripping ──────────────────────────────────────────

@register(integration="aegis_endpoint_agent", action="suid_bit_strip")
class EASuidBitStrip(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="EA-SUID",
            required=["enforcement"],
            params=params,
            detail_tmpl="would push EA policy: {enforcement!r} when AI processes "
                        "attempt chmod +s (SUID/SGID bit set) on any binary",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)


# ── 11. chmod on secret files ────────────────────────────────────────

@register(integration="aegis_endpoint_agent", action="chmod_secret_files")
class EAChmodSecretFiles(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="EA-CHSC",
            required=["enforcement"],
            params=params,
            detail_tmpl="would push EA policy: {enforcement!r} when AI processes "
                        "loosen permissions (chmod o+r, icacls grant) on secret "
                        "files (.ssh/*, .gnupg/*, .env, credentials.*)",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)


# ── 12. Model hash allowlist enforcement ─────────────────────────────

@register(integration="aegis_endpoint_agent", action="model_hash_allowlist_enforce")
class EAModelHashAllowlistEnforce(BaseMitigationAdapter):
    dry_run = True

    async def apply(self, *, credentials, params):
        return dry_apply(
            prefix="EA-MDLH",
            required=["enforcement"],
            params=params,
            detail_tmpl="would push EA policy: {enforcement!r} for local model "
                        "file loads (GGUF, safetensors, pickle) whose SHA-256 "
                        "hash is not in the tenant's approved allowlist",
        )

    async def verify(self, *, credentials, params, state_blob):
        return dry_verify(_API_LABEL, state_blob)

    async def rollback(self, *, credentials, params, state_blob):
        return dry_rollback(_API_LABEL, state_blob)
