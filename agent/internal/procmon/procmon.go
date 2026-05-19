// Package procmon — cross-platform process snapshot poller.
//
// Captures the four high-value endpoint detection categories that
// fsmon alone cannot see:
//
//   1. AI process running       cursor / claude / ollama / lm-studio /
//                                python+langchain — detect that the
//                                binary is on the host, even if no
//                                file write occurs.
//   2. curl-pipe-shell pattern  parent=curl|wget|fetch with a shell
//                                child started within ~10s. Loose
//                                correlation without parent PID, but
//                                a strong signal when both fire.
//   3. Destructive cmd while    AI binary running AND a destructive
//      AI binary active         command (rm -rf, del /q /s,
//                                Remove-Item -Recurse, git clean -fdx,
//                                docker system prune) starting within
//                                the same poll window.
//   4. Package install activity npm/pip/brew invocation observed —
//                                captures the slopsquat threat surface
//                                even before the install completes.
//
// Mechanism: 5-second polling of the OS process list. The platform-
// specific files (procmon_linux.go, procmon_darwin.go, procmon_windows.go)
// implement Snapshot() to return [{pid, ppid, name, command}].
// Command lines are SHA-256 hashed at source — the agent NEVER sends
// the plaintext command line.
//
// Why polling and not real-time? Real-time process events require
// kernel-level primitives (ETW on Windows, fanotify+netlink on Linux,
// EndpointSecurity on macOS) which need admin privilege at install
// time AND signed binaries on macOS. Polling is the universal
// no-admin floor. Native back-ends slot in via the same interface
// in a post-GA increment.
package procmon

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"strings"
	"sync"
	"time"

	"github.com/securisti/aegis-endpoint-agent/internal/events"
)

// Proc is one row from a process-list snapshot.
type Proc struct {
	PID     int
	PPID    int    // 0 when the platform back-end can't provide it
	Name    string // executable basename, lower-cased
	Command string // full command line; hashed before any network send
}

// Snapshot returns the current process list. Implemented per-OS.
func Snapshot() ([]Proc, error) { return platformSnapshot() }

// ---- AI binary inventory ---------------------------------------------------
//
// A process is considered "an AI tool" when its executable basename
// matches one of these patterns (case-insensitive substring match) OR
// its command line carries one of the AI SDK signatures.
//
// This list is deliberately conservative: false positives create
// alerting noise, and the network-connection detector (netmon) catches
// real AI traffic regardless of what the process is called.

var aiBinaryNames = []string{
	"cursor", "claude", "claude-code", "claude-desktop",
	"ollama", "lm-studio", "lmstudio", "anythingllm",
	"continue", "cline", "aider", "windsurf", "zed",
	"copilot", "codeium", "tabnine",
	"localai", "llama-server", "llama-cpp-server",
}

// AI SDK names. We only check Python / Node interpreter command lines
// for these because checking every process command line is expensive.
var aiSDKHints = []string{
	"openai", "anthropic", "langchain", "llama_index", "llamaindex",
	"transformers", "huggingface", "ollama", "litellm",
	"sentence_transformers", "guardrails", "instructor",
}

var interpreterNames = []string{"python", "python3", "node", "deno", "bun"}

// IsAIProcess returns (isAI, reason) for a single Proc. Reason is a
// short label suitable for emitting in event payloads.
func IsAIProcess(p Proc) (bool, string) {
	name := strings.ToLower(p.Name)
	for _, n := range aiBinaryNames {
		if strings.Contains(name, n) {
			return true, "ai_binary:" + n
		}
	}
	// Interpreter + AI SDK in command line.
	for _, interp := range interpreterNames {
		if strings.Contains(name, interp) {
			cmdLower := strings.ToLower(p.Command)
			for _, sdk := range aiSDKHints {
				if strings.Contains(cmdLower, sdk) {
					return true, "interpreter+sdk:" + interp + "+" + sdk
				}
			}
			break
		}
	}
	return false, ""
}

// ---- Destructive command inventory ----------------------------------------

var destructiveSignatures = []string{
	// Unix
	"rm -rf", "rm -r --no-preserve-root", "find -delete",
	"git clean -fdx", "git clean -ffdx",
	"docker system prune", "docker volume prune --all",
	"chmod -R 777", "chmod 4755", "chown -R root",
	"dd if=", // dd writing to a block device
	// Windows
	"remove-item -recurse", "remove-item -force -recurse",
	"del /q /s", "rmdir /s /q", "format c:",
	"reg delete hklm",
	// Privileged escalation patterns the AI agent should never emit
	"sudo su", "sudo -i", "runas /user:administrator",
}

// IsDestructive returns (isDestructive, signature) for a command line.
func IsDestructive(cmd string) (bool, string) {
	lc := strings.ToLower(cmd)
	for _, sig := range destructiveSignatures {
		if strings.Contains(lc, sig) {
			return true, sig
		}
	}
	return false, ""
}

// ---- Package-install command inventory ------------------------------------

var packageInstallSignatures = []string{
	"npm install ", "npm i ", "npm add ", "pnpm add ", "pnpm install ",
	"yarn add ", "yarn install",
	"pip install ", "pip3 install ", "uv pip install ",
	"poetry add ", "poetry install",
	"brew install ", "brew tap ",
	"choco install ", "winget install ", "scoop install ",
	"cargo install ",
}

// PackageInstall returns (true, ecosystem, package_name_or_url) when
// a command looks like a package install. ecosystem is one of:
// npm | pip | brew | choco | winget | scoop | cargo | unknown.
func PackageInstall(cmd string) (bool, string, string) {
	lc := strings.ToLower(cmd)
	for _, sig := range packageInstallSignatures {
		if !strings.Contains(lc, sig) {
			continue
		}
		// Extract the substring after the signature as a coarse
		// package-name token. Stop at the first whitespace.
		idx := strings.Index(lc, sig) + len(sig)
		rest := strings.TrimSpace(cmd[idx:])
		name := rest
		if sp := strings.IndexAny(rest, " \t"); sp > 0 {
			name = rest[:sp]
		}
		eco := "unknown"
		switch {
		case strings.HasPrefix(lc[strings.Index(lc, sig):], "npm"),
			strings.HasPrefix(lc[strings.Index(lc, sig):], "pnpm"),
			strings.HasPrefix(lc[strings.Index(lc, sig):], "yarn"):
			eco = "npm"
		case strings.HasPrefix(lc[strings.Index(lc, sig):], "pip"),
			strings.HasPrefix(lc[strings.Index(lc, sig):], "uv pip"),
			strings.HasPrefix(lc[strings.Index(lc, sig):], "poetry"):
			eco = "pip"
		case strings.HasPrefix(lc[strings.Index(lc, sig):], "brew"):
			eco = "brew"
		case strings.HasPrefix(lc[strings.Index(lc, sig):], "choco"):
			eco = "choco"
		case strings.HasPrefix(lc[strings.Index(lc, sig):], "winget"):
			eco = "winget"
		case strings.HasPrefix(lc[strings.Index(lc, sig):], "scoop"):
			eco = "scoop"
		case strings.HasPrefix(lc[strings.Index(lc, sig):], "cargo"):
			eco = "cargo"
		}
		return true, eco, name
	}
	return false, "", ""
}

// ---- Monitor ------------------------------------------------------------

type Monitor struct {
	out        chan events.Event
	tickFast   time.Duration
	tickSteady time.Duration
	rampUntil  time.Time

	mu          sync.Mutex
	seenProcs   map[int]string // pid -> name; lets us emit only on START, not every tick
	aiActive    map[int]bool   // pid -> true while an AI binary is running
	cancel      context.CancelFunc
}

func New() *Monitor {
	return &Monitor{
		tickFast:   5 * time.Second,
		tickSteady: 15 * time.Second,
		rampUntil:  time.Now().Add(5 * time.Minute),
		seenProcs:  map[int]string{},
		aiActive:   map[int]bool{},
	}
}

func (m *Monitor) Start(ctx context.Context) (<-chan events.Event, error) {
	subCtx, cancel := context.WithCancel(ctx)
	m.cancel = cancel
	m.out = make(chan events.Event, 256)
	go m.loop(subCtx)
	return m.out, nil
}

func (m *Monitor) Stop() {
	if m.cancel != nil {
		m.cancel()
	}
}

func (m *Monitor) Name() string { return "procmon-poll" }

func (m *Monitor) loop(ctx context.Context) {
	defer close(m.out)
	// Seed once so already-running processes don't all alert.
	if initial, err := Snapshot(); err == nil {
		m.mu.Lock()
		for _, p := range initial {
			m.seenProcs[p.PID] = p.Name
			if ok, _ := IsAIProcess(p); ok {
				m.aiActive[p.PID] = true
			}
		}
		m.mu.Unlock()
	}

	t := time.NewTimer(m.currentTick())
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			m.tick()
			t.Reset(m.currentTick())
		}
	}
}

func (m *Monitor) currentTick() time.Duration {
	if time.Now().Before(m.rampUntil) {
		return m.tickFast
	}
	return m.tickSteady
}

// hashCmd is the source-side privacy guard. The plaintext command
// line NEVER leaves the host — the backend only ever sees the SHA.
func hashCmd(s string) string {
	h := sha256.Sum256([]byte(s))
	return hex.EncodeToString(h[:])
}

func (m *Monitor) tick() {
	procs, err := Snapshot()
	if err != nil {
		// Best-effort — log via the OS later if needed. Skip this tick.
		return
	}

	m.mu.Lock()
	defer m.mu.Unlock()

	currentPIDs := make(map[int]bool, len(procs))
	aiStillActive := make(map[int]bool, len(m.aiActive))

	for _, p := range procs {
		currentPIDs[p.PID] = true

		// AI binary lifecycle (start detection)
		if isAI, reason := IsAIProcess(p); isAI {
			if !m.aiActive[p.PID] {
				m.out <- events.AIProcessRunning(p.Name, reason, hashCmd(p.Command))
			}
			aiStillActive[p.PID] = true
		}

		// New process this tick? Most ticks the proc list is mostly
		// stable — emit only on actual creation.
		if _, had := m.seenProcs[p.PID]; had {
			continue
		}

		// Process started this tick. Apply detection rules.

		// 1. Destructive command anywhere on the host while ANY AI
		//    binary is active. Loose correlation but a strong signal.
		if dest, sig := IsDestructive(p.Command); dest {
			if len(m.aiActive) > 0 || len(aiStillActive) > 0 {
				m.out <- events.DestructiveCmdCorrelation(p.Name, sig, hashCmd(p.Command))
			}
		}

		// 2. curl|sh: parent (already-seen) is curl/wget/fetch and a
		//    shell starts. On Windows pwsh / powershell. Without
		//    parent PID we approximate: any sh/pwsh started while a
		//    curl/wget process is currently in the snapshot.
		if isShell(p.Name) && curlActive(procs) {
			m.out <- events.CurlPipeShellSuspected(p.Name, hashCmd(p.Command))
		}

		// 3. Package install. Emit regardless of AI context — slopsquat
		//    detection needs every install, then backend matches the
		//    package name against OSV.
		if inst, eco, pkg := PackageInstall(p.Command); inst {
			// pkg is a coarse first-token; never the full command line.
			m.out <- events.PackageInstallObserved(eco, pkg, hashCmd(p.Command))
		}
	}

	// Reconcile: drop PIDs no longer present.
	for pid := range m.seenProcs {
		if !currentPIDs[pid] {
			delete(m.seenProcs, pid)
		}
	}
	for _, p := range procs {
		m.seenProcs[p.PID] = p.Name
	}
	m.aiActive = aiStillActive
}

func isShell(name string) bool {
	n := strings.ToLower(name)
	for _, s := range []string{"sh", "bash", "zsh", "fish", "ksh",
		"pwsh", "powershell", "cmd"} {
		if n == s || n == s+".exe" {
			return true
		}
	}
	return false
}

func curlActive(procs []Proc) bool {
	for _, p := range procs {
		n := strings.ToLower(p.Name)
		if n == "curl" || n == "curl.exe" ||
			n == "wget" || n == "wget.exe" ||
			n == "fetch" || n == "iwr" ||
			strings.Contains(strings.ToLower(p.Command), "invoke-webrequest") {
			return true
		}
	}
	return false
}
