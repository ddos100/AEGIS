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
	"syscall"
	"time"

	"github.com/securisti/aegis-endpoint-agent/internal/config"
	"github.com/securisti/aegis-endpoint-agent/internal/enrollment"
	"github.com/securisti/aegis-endpoint-agent/internal/events"
	"github.com/securisti/aegis-endpoint-agent/internal/fsmon"
	"github.com/securisti/aegis-endpoint-agent/internal/ingest"
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

	// Heartbeat ticker (60 s — matches /enroll response default).
	heartbeat := time.NewTicker(time.Duration(cfg.HeartbeatSeconds) * time.Second)
	defer heartbeat.Stop()

	// Flush ticker (10 s) — pushes the batched events to the backend.
	flush := time.NewTicker(10 * time.Second)
	defer flush.Stop()

	log.Printf("aegis-ea: running as device %s, version %s, fsmon=%s",
		cfg.DeviceID, AgentVersion, mon.Name())

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
