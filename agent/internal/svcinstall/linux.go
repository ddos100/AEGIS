//go:build linux

package svcinstall

import (
	"fmt"
	"os"
	"os/exec"
	"strings"
)

const unitPath = "/etc/systemd/system/aegis-ea.service"

// Install creates and starts a systemd unit for the agent.
func Install(configPath string) error {
	exe, err := selfExe()
	if err != nil {
		return err
	}

	unit := strings.Join([]string{
		"[Unit]",
		"Description=" + Description,
		"Documentation=https://docs.securisti.com/aegis/endpoint-agent",
		"After=network-online.target",
		"Wants=network-online.target",
		"",
		"[Service]",
		"Type=simple",
		fmt.Sprintf("ExecStart=%s --config %s", exe, configPath),
		"Restart=on-failure",
		"RestartSec=10",
		"WatchdogSec=300",
		"# Resource limits — the agent must not starve the host.",
		"MemoryMax=128M",
		"CPUQuota=5%",
		"# Security hardening",
		"NoNewPrivileges=true",
		"ProtectSystem=strict",
		"ProtectHome=read-only",
		"PrivateTmp=true",
		"ReadWritePaths=/var/lib/aegis-ea /tmp",
		"# Logging — structured JSON goes to journald.",
		"StandardOutput=journal",
		"StandardError=journal",
		"SyslogIdentifier=aegis-ea",
		"",
		"[Install]",
		"WantedBy=multi-user.target",
	}, "\n")

	if err := os.WriteFile(unitPath, []byte(unit+"\n"), 0644); err != nil {
		return fmt.Errorf("write unit file: %w", err)
	}

	// Ensure state directory exists.
	_ = os.MkdirAll("/var/lib/aegis-ea", 0750)

	cmds := [][]string{
		{"systemctl", "daemon-reload"},
		{"systemctl", "enable", ServiceName},
		{"systemctl", "restart", ServiceName},
	}
	for _, argv := range cmds {
		out, err := exec.Command(argv[0], argv[1:]...).CombinedOutput()
		if err != nil {
			return fmt.Errorf("%s: %w\n%s", strings.Join(argv, " "), err, out)
		}
	}
	fmt.Printf("aegis-ea: installed systemd unit → %s\n", unitPath)
	fmt.Println("aegis-ea: service enabled and started")
	fmt.Println("aegis-ea: check status:  systemctl status aegis-ea")
	fmt.Println("aegis-ea: view logs:     journalctl -u aegis-ea -f")
	return nil
}

// Uninstall stops and removes the systemd unit.
func Uninstall() error {
	cmds := [][]string{
		{"systemctl", "stop", ServiceName},
		{"systemctl", "disable", ServiceName},
	}
	for _, argv := range cmds {
		// Ignore errors — service may already be stopped/disabled.
		_, _ = exec.Command(argv[0], argv[1:]...).CombinedOutput()
	}
	if err := os.Remove(unitPath); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("remove unit: %w", err)
	}
	_, _ = exec.Command("systemctl", "daemon-reload").CombinedOutput()
	fmt.Println("aegis-ea: systemd unit removed")
	return nil
}
