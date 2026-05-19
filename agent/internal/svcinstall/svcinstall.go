// Package svcinstall installs / uninstalls the AEGIS Endpoint Agent
// as an OS service so it starts automatically on boot and survives
// user logoff.
//
//   Linux  — systemd unit file in /etc/systemd/system/
//   macOS  — launchd plist in /Library/LaunchDaemons/
//   Windows — sc.exe (Service Control Manager)
//
// All three paths are idempotent: installing when already installed
// updates the unit; uninstalling when not installed is a no-op.
//
// The binary path baked into the service definition is the absolute
// path of the currently running executable (os.Executable()).
//
// Public API (defined per-platform via build tags):
//
//	svcinstall.Install(configPath string) error
//	svcinstall.Uninstall() error
package svcinstall

import (
	"fmt"
	"os"
	"path/filepath"
)

const (
	// ServiceName is the OS-level service / daemon name.
	ServiceName = "aegis-ea"
	// DisplayName is human-readable (Windows Services UI, journalctl).
	DisplayName = "AEGIS Endpoint Agent"
	// Description shown in service managers.
	Description = "AI Security Posture Management — endpoint telemetry agent"
)

// selfExe returns the absolute path of the currently running binary.
func selfExe() (string, error) {
	p, err := os.Executable()
	if err != nil {
		return "", fmt.Errorf("cannot resolve own binary: %w", err)
	}
	return filepath.Abs(p)
}
