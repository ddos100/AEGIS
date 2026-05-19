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
#    If Go 1.22+ is installed: native build (fast).
#    If not: make build auto-falls-back to a Docker build, no Go needed.
make build
ls -lh build/

# 2. Have an AEGIS admin generate a one-time enrolment code in the UI
#    (POST /v1/endpoint-agent/enrollment-code).

# 3. First-run enrolment exchanges the code for a device-scoped token.
./build/aegis-ea --api-url https://aegis.example.com --enroll <CODE>

# 4. Subsequent runs are daemonised.
./build/aegis-ea

# 5. Verify the pipeline end-to-end (sends one synthetic event and exits):
./build/aegis-ea --diagnose
```

## What you'll see in the UI

The agent emits detection events only when AI tools modify files in the
watched set (Cursor / Claude Desktop / VS Code MCP configs, shell rc
files, etc.). On a freshly-installed host with no AI tools yet, only
the 60-second heartbeats are visible — that's correct behaviour, not a
bug. Use `--diagnose` to confirm the pipeline works without needing a
real AI tool present.

The portable poller emits an event the moment a watched file *appears*
post-install (not only when it's modified), so dropping a new
`mcp.json` triggers a `created` detection on the next 15 s tick. The
first 5 minutes after agent start use the 15 s fast cadence; after
that it backs off to 60 s.

### Building without Go installed on the host

The AEGIS API container already ships Go via its build stage; you do
not need a separate toolchain on the host:

```sh
make build-docker    # produces ./build/aegis-ea via docker buildx
```

### Installing Go 1.22+ (for native builds)

```sh
# Ubuntu/Debian — apt's golang-go is usually too old. Use the tarball.
curl -fsSLO https://go.dev/dl/go1.22.6.linux-amd64.tar.gz
sudo rm -rf /usr/local/go
sudo tar -C /usr/local -xzf go1.22.6.linux-amd64.tar.gz
echo 'export PATH=$PATH:/usr/local/go/bin' | sudo tee /etc/profile.d/go.sh
export PATH=$PATH:/usr/local/go/bin
go version           # go version go1.22.6 linux/amd64
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
