// Package fsmon — file-system + process monitor.
//
// `New()` returns an OS-appropriate `Monitor`. v1 uses a portable
// polling implementation across all three OSes — it scans the
// AI-tool-relevant paths every 15 s for the first 5 minutes and every
// 60 s thereafter, emitting diff events. That ramp gives operators
// fast feedback right after install + reasonable steady-state cost.
//
// The fanotify (Linux), EndpointSecurity (macOS), and ETW (Windows)
// kernel-event back-ends slot in via build-tagged files
// (fsmon_<os>.go) in a post-GA increment.
package fsmon

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"log"
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
// kernel-event back-ends ship.
type portable struct {
	out chan events.Event
	mu  sync.Mutex

	knownFiles map[string]fileSnapshot
	cancel     context.CancelFunc
}

type fileSnapshot struct {
	mode    os.FileMode
	size    int64
	modTime time.Time
	sha     string
}

// Allow-listed paths to watch. Same set documented in
// PHASE-7-PLAN.md §B.3.4. We pattern-match the path before sending
// so the backend never sees the user's absolute home path.
//
// Where conventional paths might not be set (e.g. APPDATA empty on a
// stripped-down Windows session) we fall back to UserHomeDir-relative
// candidates so the agent still has something to watch.
func watchedPathPatterns() []string {
	home, _ := os.UserHomeDir()
	out := []string{}
	if home == "" {
		return out
	}

	// Cross-OS: shell rc files (only exist on Unix, but listing them
	// on Windows is cheap and harmless — they're just always-missing).
	out = append(out,
		filepath.Join(home, ".bashrc"),
		filepath.Join(home, ".zshrc"),
		filepath.Join(home, ".profile"),
		filepath.Join(home, ".bash_profile"),
	)

	// Cross-OS AI-tool MCP configs.
	out = append(out,
		filepath.Join(home, ".cursor", "mcp.json"),
		filepath.Join(home, ".config", "claude-code", "mcp.json"),
		filepath.Join(home, ".config", "Code", "User", "mcp.json"),
	)

	switch runtime.GOOS {
	case "darwin":
		out = append(out,
			filepath.Join(home, "Library", "Application Support", "Claude", "mcp.json"),
			filepath.Join(home, "Library", "Application Support", "Cursor", "mcp.json"),
			filepath.Join(home, "Library", "Application Support", "Code", "User", "mcp.json"),
		)
	case "windows":
		// %APPDATA% / %LOCALAPPDATA% are the right roots; fall back
		// to UserHomeDir-relative paths if those env vars are missing.
		appdata := os.Getenv("APPDATA")
		if appdata == "" {
			appdata = filepath.Join(home, "AppData", "Roaming")
		}
		localApp := os.Getenv("LOCALAPPDATA")
		if localApp == "" {
			localApp = filepath.Join(home, "AppData", "Local")
		}
		out = append(out,
			filepath.Join(appdata, "Cursor", "mcp.json"),
			filepath.Join(appdata, "cursor", "mcp.json"),
			filepath.Join(appdata, "Claude", "mcp.json"),
			filepath.Join(appdata, "Code", "User", "mcp.json"),
			filepath.Join(appdata, "Code", "User", "settings.json"),
			filepath.Join(localApp, "Programs", "cursor", "resources", "app", "package.json"),
			filepath.Join(home, "Documents", "PowerShell", "Profile.ps1"),
			filepath.Join(home, "Documents", "WindowsPowerShell", "Profile.ps1"),
			// Wells where developers often drop config:
			filepath.Join(home, ".cursor", "mcp.json"),
			filepath.Join(home, ".aws", "credentials"),
			filepath.Join(home, ".ssh", "config"),
		)
	}
	return out
}

// pathPattern turns an absolute path like
// `C:\Users\alice\AppData\Roaming\Cursor\mcp.json` into a portable
// tilde-prefixed pattern. Backend only ever sees the pattern.
func pathPattern(p string) string {
	home, _ := os.UserHomeDir()
	if home != "" && strings.HasPrefix(p, home) {
		return "~" + filepath.ToSlash(p[len(home):])
	}
	return filepath.ToSlash(p)
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
	return fmt.Sprintf("portable-poll/%s", runtime.GOOS)
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

// loop is the polling driver. Fast tick (15 s) for the first 5 min so
// post-install detections show up quickly, then back off to 60 s.
func (p *portable) loop(ctx context.Context) {
	defer close(p.out)
	paths := watchedPathPatterns()
	log.Printf("aegis-ea: fsmon watching %d paths under %s",
		len(paths), pathPattern(mustHome()))
	for _, p2 := range paths {
		log.Printf("aegis-ea:   - %s", pathPattern(p2))
	}

	// Seed the snapshot so pre-existing files don't fire "appeared"
	// events. AFTER seed, both modifications AND appearances fire.
	p.poll(true)

	// Fast tick for the first 5 minutes.
	rampUntil := time.Now().Add(5 * time.Minute)
	tick := func() time.Duration {
		if time.Now().Before(rampUntil) {
			return 15 * time.Second
		}
		return 60 * time.Second
	}

	t := time.NewTimer(tick())
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			p.poll(false)
			t.Reset(tick())
		}
	}
}

func mustHome() string {
	h, _ := os.UserHomeDir()
	return h
}

func (p *portable) poll(seedOnly bool) {
	p.mu.Lock()
	defer p.mu.Unlock()
	for _, path := range watchedPathPatterns() {
		snap, ok := snapshot(path)
		if !ok {
			// File no longer exists or never did. Drop from known so
			// a later appearance will fire as "appeared".
			delete(p.knownFiles, path)
			continue
		}
		prev, had := p.knownFiles[path]
		p.knownFiles[path] = snap
		if seedOnly {
			// Seed phase — record everything silently so existing
			// files don't generate spurious "appeared" events on
			// agent restart.
			continue
		}
		if !had {
			// File appeared post-seed. This is exactly what we want
			// to catch — Cursor / Claude Desktop dropping a new
			// mcp.json, an AI tool installer writing a new shell rc,
			// etc.
			p.out <- events.FileWriteToWatchedPath(
				pathPattern(path),
				"created",
				int(snap.mode.Perm()),
				snap.sha,
			)
			if strings.HasSuffix(path, "mcp.json") {
				p.out <- events.MCPConfigObserved(
					pathPattern(path),
					[]string{}, // server names not parsed in v1
					0,
				)
			}
			continue
		}
		// Existing file changed since the prior tick.
		if prev.sha != snap.sha || prev.mode != snap.mode {
			p.out <- events.FileWriteToWatchedPath(
				pathPattern(path),
				"modified",
				int(snap.mode.Perm()),
				snap.sha,
			)
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
