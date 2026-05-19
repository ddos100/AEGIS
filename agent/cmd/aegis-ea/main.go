// AEGIS Endpoint Agent (Phase 7.6).
//
// Cross-platform observe-only daemon. Watches for AI-tool installer +
// lifecycle patterns documented in PHASE-7-PLAN.md §B.3.4 and emits
// privacy-bounded events to the AEGIS backend.
//
// Design contract
//   * Observe-only at GA. No file blocking, no process termination.
//   * Privacy: payloads carry path patterns + sha256 hashes only.
//   * Resilience: agent must survive backend outage. Events are batched
//     in memory; on send failure, the batch is retried with exponential
//     backoff up to 1 minute before being dropped (with a log line).
//   * Resource budget: agent must not exceed ~50 MB RSS or ~1% CPU on
//     a 4-core developer laptop. The portable polling fallback runs at
//     a 60-second tick; OS-native back-ends use event-driven kernel
//     primitives so steady-state CPU is near-zero.
//
// Build
//   GOOS=linux  GOARCH=amd64 go build -o build/aegis-ea_linux_amd64 ./cmd/aegis-ea
//   GOOS=darwin GOARCH=arm64 go build -o build/aegis-ea_darwin_arm64 ./cmd/aegis-ea
//   GOOS=windows GOARCH=amd64 go build -o build/aegis-ea_windows_amd64.exe ./cmd/aegis-ea
//
// The `scripts/build_all.sh` script wraps the cross-build matrix.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"log"
	"os"
	"os/signal"
	"runtime"
	"strings"
	"syscall"
	"time"

	"github.com/securisti/aegis-endpoint-agent/internal/config"
	"github.com/securisti/aegis-endpoint-agent/internal/enrollment"
	"github.com/securisti/aegis-endpoint-agent/internal/events"
	"github.com/securisti/aegis-endpoint-agent/internal/fsmon"
	"github.com/securisti/aegis-endpoint-agent/internal/ingest"
	"github.com/securisti/aegis-endpoint-agent/internal/netmon"
	"github.com/securisti/aegis-endpoint-agent/internal/procmon"
)

// AgentVersion is stamped into every event + enrolment request.
// Updated by release tooling; build with -ldflags "-X main.AgentVersion=..."
var AgentVersion = "0.1.0-dev"

func main() {
	if err := run(); err != nil {
		log.Fatalf("aegis-ea: %v", err)
	}
}

func run() error {
	cfgPath := flag.String("config", config.DefaultPath(), "Path to agent config (TOML).")
	enrollFlag := flag.String("enroll", "", "Enrollment code (one-shot).")
	apiURL := flag.String("api-url", "", "AEGIS API base URL (https://aegis.example.com)")
	versionFlag := flag.Bool("version", false, "Print version and exit.")
	diagnose := flag.Bool("diagnose", false,
		"Run end-to-end diagnostic: enumerate watched paths, send one "+
			"synthetic heartbeat + one synthetic file_write_to_watched_path "+
			"event to prove the pipeline, then exit.")
	flag.Parse()

	if *versionFlag {
		fmt.Printf("aegis-ea %s (%s/%s)\n", AgentVersion, runtime.GOOS, runtime.GOARCH)
		return nil
	}

	cfg, err := config.Load(*cfgPath)
	if err != nil && !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("load config: %w", err)
	}

	// Override config with CLI flags when explicitly set.
	if *apiURL != "" {
		cfg.APIURL = *apiURL
	}
	cfg.AgentVersion = AgentVersion

	// First-run path: exchange enrolment code for a device token.
	if *enrollFlag != "" {
		if cfg.APIURL == "" {
			return errors.New("--enroll requires --api-url or APIURL in config")
		}
		log.Printf("aegis-ea: enrolling against %s", cfg.APIURL)
		token, deviceID, ingestURL, err := enrollment.Enroll(
			cfg.APIURL, *enrollFlag, cfg.Hostname(), runtime.GOOS, runtime.GOARCH,
			AgentVersion,
		)
		if err != nil {
			return fmt.Errorf("enroll: %w", err)
		}
		cfg.AgentToken = token
		cfg.DeviceID = deviceID
		cfg.IngestURL = ingestURL
		if err := config.Save(*cfgPath, cfg); err != nil {
			return fmt.Errorf("save config: %w", err)
		}
		log.Printf("aegis-ea: enrolled device %s; config saved to %s", deviceID, *cfgPath)
		return nil
	}

	if cfg.AgentToken == "" || cfg.DeviceID == "" {
		return errors.New("agent not enrolled; run with --enroll <code>")
	}

	// Diagnostic mode: prove the pipeline end-to-end without waiting
	// for an AI tool to do something interesting. Sends one
	// synthetic event of each major kind + the heartbeat and exits.
	if *diagnose {
		ctx, cancel := context.WithCancel(context.Background())
		defer cancel()
		client := ingest.NewClient(cfg.IngestURL, cfg.AgentToken, cfg.DeviceID)
		log.Print("==================================================================")
		log.Print("aegis-ea diagnose: end-to-end pipeline verification")
		log.Print("==================================================================")
		log.Printf("  device_id   : %s", cfg.DeviceID)
		log.Printf("  api_url     : %s", cfg.APIURL)
		log.Printf("  ingest_url  : %s", cfg.IngestURL)
		log.Printf("  token (len) : %d chars", len(cfg.AgentToken))
		log.Printf("  os/arch     : %s/%s", runtime.GOOS, runtime.GOARCH)
		mon := fsmon.New()
		log.Printf("  fsmon back-end : %s", mon.Name())
		log.Print("------------------------------------------------------------------")

		// Sanity check: ingest URL must be absolute. A common failure
		// mode is a relative ingest_url surviving in config.json, which
		// the Go http.Client cannot reach.
		if !(strings.HasPrefix(cfg.IngestURL, "http://") ||
			strings.HasPrefix(cfg.IngestURL, "https://")) {
			return fmt.Errorf(
				"ingest_url is not absolute: %q — re-enrol with "+
					"--api-url http://your-aegis-host to fix",
				cfg.IngestURL,
			)
		}

		// Send each event individually so the operator sees per-event
		// success/failure rather than a single all-or-nothing result.
		type step struct {
			name string
			evt  events.Event
		}
		steps := []step{
			{"heartbeat", events.Heartbeat(AgentVersion)},
			{"file_write_to_watched_path (synthetic)",
				events.FileWriteToWatchedPath(
					"~/.aegis-ea-diagnose.marker", "created", 0o600,
					"diagnose-placeholder-sha256",
				)},
			{"process_exec (synthetic)",
				events.ProcessExec(
					"aegis-ea", "diagnose-binary-sha", "shell",
					"shell-sha", "diagnose-command-sha",
				)},
		}
		sent := 0
		for i, s := range steps {
			err := client.Flush(ctx, []events.Event{s.evt})
			if err != nil {
				log.Printf("  [%d/%d] %-44s FAIL: %v",
					i+1, len(steps), s.name, err)
				log.Print("------------------------------------------------------------------")
				log.Printf("  diagnose stopped after %d/%d events.", sent, len(steps))
				log.Print("  Common causes:")
				log.Print("    * Backend unreachable (curl/Test-NetConnection it manually)")
				log.Print("    * Wrong API URL or token (re-run --enroll)")
				log.Print("    * Device revoked (check Endpoint agents page)")
				log.Print("    * Reverse-proxy / firewall blocking /v1/ingest/endpoint-agent")
				return fmt.Errorf("diagnose flush failed: %w", err)
			}
			log.Printf("  [%d/%d] %-44s OK",
				i+1, len(steps), s.name)
			sent++
		}

		log.Print("------------------------------------------------------------------")
		log.Printf("  SUCCESS — %d synthetic events accepted by the backend.", sent)
		// Build a clickable URL pointing at the Endpoint Agents page.
		uiBase := strings.TrimSuffix(cfg.APIURL, "/v1")
		uiBase = strings.TrimSuffix(uiBase, "/")
		log.Printf("  Open: %s/endpoint-agents", uiBase)
		log.Print("  Scroll to the 'Recent events (last 100)' panel — the three")
		log.Print("  events above should appear within seconds.")
		log.Print("==================================================================")
		log.Print("NOTE: --diagnose events do NOT appear on the Discovery page.")
		log.Print("      Discovery shows the Shadow AI Radar (WS) + ai_usage_events")
		log.Print("      (network/XDR ingest). EA events live under /endpoint-agents.")
		log.Print("==================================================================")
		return nil
	}

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Graceful shutdown on SIGINT / SIGTERM.
	sigCh := make(chan os.Signal, 1)
	signal.Notify(sigCh, os.Interrupt, syscall.SIGTERM)
	go func() {
		<-sigCh
		log.Print("aegis-ea: shutdown signal received")
		cancel()
	}()

	client := ingest.NewClient(cfg.IngestURL, cfg.AgentToken, cfg.DeviceID)
	eventBuf := events.NewBuffer(500)

	// File-system monitor — OS-specific back-end selected by build tag,
	// falling back to portable polling if the native primitive isn't
	// available at runtime.
	mon := fsmon.New()
	monEvents, err := mon.Start(ctx)
	if err != nil {
		return fmt.Errorf("fsmon start: %w", err)
	}
	defer mon.Stop()

	// Process monitor — polls the OS process table to detect AI binaries
	// running, curl|sh patterns, destructive commands while AI is
	// active, and package install activity. v0.2.0 addition.
	pm := procmon.New()
	procEvents, err := pm.Start(ctx)
	if err != nil {
		return fmt.Errorf("procmon start: %w", err)
	}
	defer pm.Stop()

	// Network monitor — resolves AI provider domains to current IPs and
	// polls active TCP connections to emit (process, domain) pairs.
	// Catches API calls that fsmon alone can't see. v0.2.0 addition.
	nm := netmon.New()
	netEvents, err := nm.Start(ctx)
	if err != nil {
		return fmt.Errorf("netmon start: %w", err)
	}
	defer nm.Stop()

	// Heartbeat ticker (60 s — matches /enroll response default).
	heartbeat := time.NewTicker(time.Duration(cfg.HeartbeatSeconds) * time.Second)
	defer heartbeat.Stop()

	// Flush ticker (10 s) — pushes the batched events to the backend.
	flush := time.NewTicker(10 * time.Second)
	defer flush.Stop()

	log.Printf("aegis-ea: running as device %s, version %s",
		cfg.DeviceID, AgentVersion)
	log.Printf("aegis-ea: fsmon=%s procmon=%s netmon=%s",
		mon.Name(), pm.Name(), nm.Name())
	log.Printf("aegis-ea: ingest=%s heartbeat=%ds batch=%d",
		cfg.IngestURL, cfg.HeartbeatSeconds, cfg.BatchSize)
	log.Print("aegis-ea: capturing — file-system events on watched AI-tool paths, " +
		"AI-tool process starts (cursor / claude / ollama / python+openai SDK ...), " +
		"AI provider connections (api.openai.com, api.anthropic.com, api.cursor.sh ...), " +
		"destructive shell commands while AI is active, curl|sh installer patterns, " +
		"and npm/pip/brew package installs. " +
		"Privacy: command lines hashed at source; never sent in plaintext.")

	for {
		select {
		case <-ctx.Done():
			_ = client.Flush(ctx, eventBuf.Drain())
			return nil
		case evt, ok := <-monEvents:
			if !ok {
				return errors.New("fsmon channel closed unexpectedly")
			}
			eventBuf.Append(evt)
			if eventBuf.Len() >= cfg.BatchSize {
				if err := client.Flush(ctx, eventBuf.Drain()); err != nil {
					log.Printf("aegis-ea: flush error: %v", err)
				}
			}
		case evt, ok := <-procEvents:
			if !ok {
				return errors.New("procmon channel closed unexpectedly")
			}
			eventBuf.Append(evt)
			if eventBuf.Len() >= cfg.BatchSize {
				if err := client.Flush(ctx, eventBuf.Drain()); err != nil {
					log.Printf("aegis-ea: flush error: %v", err)
				}
			}
		case evt, ok := <-netEvents:
			if !ok {
				return errors.New("netmon channel closed unexpectedly")
			}
			eventBuf.Append(evt)
			if eventBuf.Len() >= cfg.BatchSize {
				if err := client.Flush(ctx, eventBuf.Drain()); err != nil {
					log.Printf("aegis-ea: flush error: %v", err)
				}
			}
		case <-flush.C:
			if eventBuf.Len() > 0 {
				if err := client.Flush(ctx, eventBuf.Drain()); err != nil {
					log.Printf("aegis-ea: flush error: %v", err)
				}
			}
		case <-heartbeat.C:
			eventBuf.Append(events.Heartbeat(AgentVersion))
			if err := client.Flush(ctx, eventBuf.Drain()); err != nil {
				log.Printf("aegis-ea: heartbeat flush error: %v", err)
			}
		}
	}
}
