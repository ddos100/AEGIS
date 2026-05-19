// Package events — event buffer + builders for the AEGIS Endpoint Agent.
//
// Schema mirrors api/app/schemas/endpoint_agent.py — the backend's
// allow-list will reject anything not on this set, so the agent
// constructs events strictly from these factory functions.
//
// Privacy: every field carried here is hashed / pattern-ised at the
// source. The agent NEVER sends URL paths, command-line plaintext,
// file contents, or input fields. SHA-256 of command-line + a
// per-device salt is the only command-line surface the backend sees.
package events

import (
	"sync"
	"time"
)

type Event struct {
	Kind       string         `json:"kind"`
	OccurredAt time.Time      `json:"occurred_at"`
	Payload    map[string]any `json:"payload"`
}

// Buffer is an in-memory bounded ring; on overflow the oldest events
// are dropped (with a counter the agent reports as a metric).
type Buffer struct {
	mu       sync.Mutex
	cap      int
	items    []Event
	overflow int
}

func NewBuffer(cap int) *Buffer { return &Buffer{cap: cap} }

func (b *Buffer) Append(e Event) {
	b.mu.Lock()
	defer b.mu.Unlock()
	if len(b.items) >= b.cap {
		// Drop oldest (head) — keep newest end. Count the overflow for
		// reporting via the heartbeat payload.
		b.items = b.items[1:]
		b.overflow++
	}
	b.items = append(b.items, e)
}

func (b *Buffer) Len() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return len(b.items)
}

func (b *Buffer) Drain() []Event {
	b.mu.Lock()
	defer b.mu.Unlock()
	out := b.items
	b.items = nil
	return out
}

// --- factory helpers — exposed to fsmon back-ends ---

func ProcessExec(processName, processSHA, parentName, parentSHA, cmdLineSHA string) Event {
	return Event{
		Kind:       "process_exec",
		OccurredAt: time.Now().UTC(),
		Payload: map[string]any{
			"process_name":          processName,
			"process_sha256":        processSHA,
			"parent_process_name":   parentName,
			"parent_process_sha256": parentSHA,
			"command_line_sha256":   cmdLineSHA,
		},
	}
}

func FileWriteToWatchedPath(pathPattern, eventType string, newMode int, contentSHA string) Event {
	return Event{
		Kind:       "file_write_to_watched_path",
		OccurredAt: time.Now().UTC(),
		Payload: map[string]any{
			"path_pattern":    pathPattern,
			"event_type":      eventType,
			"new_mode":        newMode,
			"content_sha256":  contentSHA,
		},
	}
}

func SecretReadByAIProc(pathPattern, processName, processSHA string) Event {
	return Event{
		Kind:       "secret_read_by_ai_proc",
		OccurredAt: time.Now().UTC(),
		Payload: map[string]any{
			"path_pattern":   pathPattern,
			"process_name":   processName,
			"process_sha256": processSHA,
		},
	}
}

func CurlPipeShDetected(parentName, originatingDomain string, depth int) Event {
	return Event{
		Kind:       "curl_pipe_sh_detected",
		OccurredAt: time.Now().UTC(),
		Payload: map[string]any{
			"parent_process_name": parentName,
			"originating_domain":  originatingDomain,
			"process_tree_depth":  depth,
		},
	}
}

func MCPConfigObserved(configPathPattern string, servers []string, maxScopeDepth int) Event {
	return Event{
		Kind:       "mcp_config_observed",
		OccurredAt: time.Now().UTC(),
		Payload: map[string]any{
			"config_path_pattern": configPathPattern,
			"servers":             servers,
			"max_scope_depth":     maxScopeDepth,
		},
	}
}

func PackageInstallPreHook(name, version, ecosystem, installerSHA string) Event {
	return Event{
		Kind:       "package_install_pre_hook",
		OccurredAt: time.Now().UTC(),
		Payload: map[string]any{
			"package_name":     name,
			"package_version":  version,
			"ecosystem":        ecosystem,
			"installer_sha256": installerSHA,
		},
	}
}

func PathShadowDetected(binaryName, shadowPath, shadowSHA string) Event {
	return Event{
		Kind:       "path_shadow_detected",
		OccurredAt: time.Now().UTC(),
		Payload: map[string]any{
			"binary_name":   binaryName,
			"shadow_path":   shadowPath,
			"shadow_sha256": shadowSHA,
		},
	}
}

func AutostartArtifact(pathPattern, execName, execSHA string) Event {
	return Event{
		Kind:       "autostart_artifact",
		OccurredAt: time.Now().UTC(),
		Payload: map[string]any{
			"artifact_path_pattern": pathPattern,
			"exec_name":             execName,
			"exec_sha256":           execSHA,
		},
	}
}

func Heartbeat(agentVersion string) Event {
	return Event{
		Kind:       "heartbeat",
		OccurredAt: time.Now().UTC(),
		Payload: map[string]any{
			"uptime_seconds": int(time.Since(startedAt).Seconds()),
			"agent_version":  agentVersion,
		},
	}
}

// AIProcessRunning fires once per AI-tool process start.
// `reason` is a short label like "ai_binary:cursor" or
// "interpreter+sdk:python+openai".
func AIProcessRunning(processName, reason, cmdLineSHA string) Event {
	return Event{
		Kind:       "ai_process_running",
		OccurredAt: time.Now().UTC(),
		Payload: map[string]any{
			"process_name":        processName,
			"detection_reason":    reason,
			"command_line_sha256": cmdLineSHA,
		},
	}
}

// AIProviderConnection fires once per (process, AI-provider-domain)
// pair per 5-minute dedup window. Carries the domain string but
// NEVER the remote IP, port, URL path, or any payload bytes.
func AIProviderConnection(processName, providerDomain string) Event {
	return Event{
		Kind:       "ai_provider_connection",
		OccurredAt: time.Now().UTC(),
		Payload: map[string]any{
			"process_name":    processName,
			"provider_domain": providerDomain,
		},
	}
}

// DestructiveCmdCorrelation fires when a destructive command (rm -rf,
// del /q /s, etc.) is observed while any AI binary is also active on
// the host. Loose correlation — without parent PID we can't prove
// causation, but the co-occurrence is operationally interesting.
func DestructiveCmdCorrelation(processName, signature, cmdLineSHA string) Event {
	return Event{
		Kind:       "destructive_cmd_correlation",
		OccurredAt: time.Now().UTC(),
		Payload: map[string]any{
			"process_name":        processName,
			"matched_signature":   signature,
			"command_line_sha256": cmdLineSHA,
		},
	}
}

// CurlPipeShellSuspected fires when a shell starts while curl/wget is
// also live in the process table. Conservative — not all such
// co-occurrences are malicious, but the pattern matches the install
// vector documented in PHASE-7-PLAN.md §B.3 / T-0010.
func CurlPipeShellSuspected(shellName, cmdLineSHA string) Event {
	_ = shellName
	_ = cmdLineSHA
	return Event{
		Kind:       "curl_pipe_sh_detected",
		OccurredAt: time.Now().UTC(),
		Payload: map[string]any{
			"parent_process_name": "curl-or-wget",
			"originating_domain":  "unknown",
			"process_tree_depth":  0,
		},
	}
}

// PackageInstallObserved fires for each npm/pip/brew/etc. install
// command we see in the process table. Backend cross-references the
// package name against OSV.dev advisories.
func PackageInstallObserved(ecosystem, packageName, cmdLineSHA string) Event {
	return Event{
		Kind:       "package_install_pre_hook",
		OccurredAt: time.Now().UTC(),
		Payload: map[string]any{
			"package_name":     packageName,
			"package_version":  "unknown",
			"ecosystem":        ecosystem,
			"installer_sha256": cmdLineSHA,
		},
	}
}

var startedAt = time.Now()
