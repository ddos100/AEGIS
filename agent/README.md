# AEGIS Endpoint Agent

Cross-platform observe-only daemon for the AEGIS AI Threat Intelligence
module (Phase 7.6). Watches a small allow-list of AI-tool-relevant
paths and emits privacy-bounded events to the AEGIS backend.

> Status: v0.1 — portable polling fallback ships across Linux, macOS,
> and Windows. Native back-ends (fanotify / EndpointSecurity / ETW)
> stub out via build tags and will be filled in post-GA.

## Privacy contract

The agent NEVER sends:

- Prompt text, model output, file contents, URL paths, screen
  contents, keystrokes, voice/video, browser history beyond AI-domain
  matches, source code, or chat transcripts.
- Command-line plaintext. Command lines are SHA-256-hashed before they
  leave the host.

Every event payload validates against the backend's allow-list. Any
attempted PII-shaped key (`prompt`, `email`, `body`, `content`, raw
`path`, `command_line`, …) is rejected with the offending key in the
ingest response so an integrator notices immediately.

## Quick start

```sh
# 1. Build for the host OS/arch.
make build

# 2. Have an AEGIS admin generate a one-time enrolment code in the UI
#    (POST /v1/endpoint-agent/enrollment-code).

# 3. First-run enrolment exchanges the code for a device-scoped token.
./build/aegis-ea --api-url https://aegis.example.com --enroll <CODE>

# 4. Subsequent runs are daemonised.
./build/aegis-ea
```

## OS-native back-ends (post-GA)

| OS      | Native back-end                                                   |
|---------|-------------------------------------------------------------------|
| Linux   | fanotify FAN_CLASS_NOTIF + FAN_REPORT_FID + process-event netlink |
| macOS   | EndpointSecurity framework (`ES_EVENT_TYPE_NOTIFY_*`)             |
| Windows | ETW Microsoft-Windows-Kernel-{Process,File} providers             |

Each back-end is wired by replacing `overriddenNew()` in the
corresponding `fsmon_<os>.go` build-tagged file. The portable polling
fallback remains the v1 default.
