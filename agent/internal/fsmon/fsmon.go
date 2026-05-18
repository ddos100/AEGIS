// Package fsmon — file-system + process monitor.
//
// `New()` returns an OS-appropriate `Monitor`. v1 uses a portable
// polling implementation across all three OSes — it scans the
// AI-tool-relevant paths every 60 s and emits diff events. This is
// observably accurate (Phase 7.6's "observe-only at GA") at the cost
// of latency vs a true kernel-event watcher. Real fanotify (Linux),
// EndpointSecurity (macOS), and ETW (Windows) back-ends slot in via
// build-tagged files (fsmon_linux.go etc) when those native
// integrations land in a post-GA increment.
package fsmon

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"

	"github.com/securisti/aegis-endpoint-agent/internal/events"
)

// Monitor is what the agent's main loop talks to. Concrete back-ends
// are constructed by `New()` based on runtime.GOOS.
type Monitor interface {
	Start(ctx context.Context) (<-chan events.Event, error)
	Stop()
	Name() string
}

// portable is the v1 fallback used across all three OSes until
// kernel-event back-ends ship. It runs a 60-second polling loop over
// a small allow-list of AI-tool-relevant paths.
type portable struct {
	out chan events.Event
	mu  sync.Mutex

	// State for the diff loop.
	knownFiles map[string]fileSnapshot // canonical path → snapshot

	// Cancel function captured at Start().
	cancel context.CancelFunc
}

type fileSnapshot struct {
	mode    os.FileMode
	size    int64
	modTime time.Time
	sha     string
}

// Allow-listed paths to watch. Same set documented in PHASE-7-PLAN.md
// §B.3.4. We pattern-match the path before sending so the backend
// never sees the user's absolute home path.
func watchedPathPatterns() []string {
	home, _ := os.UserHomeDir()
	out := []string{}
	if home != "" {
		out = append(out,
			filepath.Join(home, ".bashrc"),
			filepath.Join(home, ".zshrc"),
			filepath.Join(home, ".profile"),
			filepath.Join(home, ".bash_profile"),
			filepath.Join(home, ".cursor", "mcp.json"),
			filepath.Join(home, ".config", "claude-code", "mcp.json"),
			filepath.Join(home, ".config", "Code", "User", "mcp.json"),
		)
		switch runtime.GOOS {
		case "darwin":
			out = append(out,
				filepath.Join(home, "Library", "Application Support", "Claude", "mcp.json"),
			)
		case "windows":
			out = append(out,
				filepath.Join(os.Getenv("APPDATA"), "cursor", "mcp.json"),
				filepath.Join(os.Getenv("APPDATA"), "Claude", "mcp.json"),
				filepath.Join(os.Getenv("APPDATA"), "Code", "User", "mcp.json"),
			)
		}
	}
	return out
}

// Pattern-isation: turn an absolute path like
// `/home/alice/.cursor/mcp.json` into `~/.cursor/mcp.json`. The backend
// only ever sees the pattern, not the home directory.
func pathPattern(p string) string {
	home, _ := os.UserHomeDir()
	if home != "" && strings.HasPrefix(p, home) {
		return "~" + p[len(home):]
	}
	return p
}

func fileSHA(p string) string {
	f, err := os.Open(p)
	if err != nil {
		return ""
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, io.LimitReader(f, 1<<20)); err != nil {
		return ""
	}
	return hex.EncodeToString(h.Sum(nil))
}

// snapshot loads (mode, size, mtime, sha) for one path.
func snapshot(p string) (fileSnapshot, bool) {
	st, err := os.Stat(p)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return fileSnapshot{}, false
		}
		return fileSnapshot{}, false
	}
	if st.IsDir() {
		return fileSnapshot{}, false
	}
	return fileSnapshot{
		mode: st.Mode(), size: st.Size(), modTime: st.ModTime(), sha: fileSHA(p),
	}, true
}

func (p *portable) Name() string {
	return fmt.Sprintf("portable-poll-60s/%s", runtime.GOOS)
}

func (p *portable) Start(ctx context.Context) (<-chan events.Event, error) {
	subCtx, cancel := context.WithCancel(ctx)
	p.cancel = cancel
	p.out = make(chan events.Event, 64)
	p.knownFiles = make(map[string]fileSnapshot)

	go p.loop(subCtx)
	return p.out, nil
}

func (p *portable) Stop() {
	if p.cancel != nil {
		p.cancel()
	}
}

// loop is the polling driver.
func (p *portable) loop(ctx context.Context) {
	defer close(p.out)
	t := time.NewTicker(60 * time.Second)
	defer t.Stop()
	// Seed snapshot at start so we don't emit "new file" events for
	// pre-existing config files.
	p.poll(true)
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			p.poll(false)
		}
	}
}

func (p *portable) poll(seedOnly bool) {
	p.mu.Lock()
	defer p.mu.Unlock()
	for _, path := range watchedPathPatterns() {
		snap, ok := snapshot(path)
		if !ok {
			delete(p.knownFiles, path)
			continue
		}
		prev, had := p.knownFiles[path]
		p.knownFiles[path] = snap
		if seedOnly || !had {
			continue
		}
		// Emit file_write_to_watched_path on (sha change) OR (mode change).
		if prev.sha != snap.sha || prev.mode != snap.mode {
			p.out <- events.FileWriteToWatchedPath(
				pathPattern(path),
				"modified",
				int(snap.mode.Perm()),
				snap.sha,
			)
			// MCP config files get a follow-up `mcp_config_observed`
			// event so the backend can flag the scope.
			if strings.HasSuffix(path, "mcp.json") {
				p.out <- events.MCPConfigObserved(
					pathPattern(path),
					[]string{}, // server names not parsed in v1
					0,
				)
			}
		}
	}
}

// New returns the OS-appropriate monitor. The portable polling
// implementation is the v1 fallback used everywhere; build-tagged
// files override this via overriddenNew() when they're present.
func New() Monitor {
	if m := overriddenNew(); m != nil {
		return m
	}
	return &portable{}
}
