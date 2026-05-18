// Package config — agent runtime configuration.
//
// Stored as TOML at a per-OS conventional path. Permission mode 0600
// on Unix to honour the "AI tool secrets must not be world-readable"
// rule the agent itself enforces against AI tools — we hold ourselves
// to the same standard.
package config

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"runtime"
)

type Config struct {
	APIURL           string `json:"api_url,omitempty"`
	IngestURL        string `json:"ingest_url,omitempty"`
	AgentToken       string `json:"agent_token,omitempty"`
	DeviceID         string `json:"device_id,omitempty"`
	AgentVersion     string `json:"agent_version,omitempty"`
	HeartbeatSeconds int    `json:"heartbeat_seconds,omitempty"`
	BatchSize        int    `json:"batch_size,omitempty"`
}

// Hostname returns the OS hostname; the agent stores it server-side so
// the operator UI can identify devices in the fleet.
func (c *Config) Hostname() string {
	h, err := os.Hostname()
	if err != nil || h == "" {
		return "unknown"
	}
	return h
}

// DefaultPath returns the per-OS path the agent reads/writes its config.
func DefaultPath() string {
	switch runtime.GOOS {
	case "linux":
		if x := os.Getenv("AEGIS_EA_CONFIG"); x != "" {
			return x
		}
		if x := os.Getenv("XDG_CONFIG_HOME"); x != "" {
			return filepath.Join(x, "aegis-ea", "config.json")
		}
		home, _ := os.UserHomeDir()
		return filepath.Join(home, ".config", "aegis-ea", "config.json")
	case "darwin":
		home, _ := os.UserHomeDir()
		return filepath.Join(home, "Library", "Application Support", "aegis-ea", "config.json")
	case "windows":
		appdata := os.Getenv("APPDATA")
		if appdata == "" {
			home, _ := os.UserHomeDir()
			appdata = filepath.Join(home, "AppData", "Roaming")
		}
		return filepath.Join(appdata, "aegis-ea", "config.json")
	default:
		return "aegis-ea.config.json"
	}
}

// Load reads a config file; returns an empty Config with sensible
// defaults if the file is missing.
func Load(path string) (*Config, error) {
	c := &Config{
		HeartbeatSeconds: 60,
		BatchSize:        100,
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return c, err
		}
		return nil, err
	}
	if err := json.Unmarshal(raw, c); err != nil {
		return nil, err
	}
	if c.HeartbeatSeconds == 0 {
		c.HeartbeatSeconds = 60
	}
	if c.BatchSize == 0 {
		c.BatchSize = 100
	}
	return c, nil
}

// Save writes config with mode 0600 (Unix) — same standard the agent
// asserts on AI tools.
func Save(path string, c *Config) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o700); err != nil {
		return err
	}
	raw, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, raw, 0o600)
}
