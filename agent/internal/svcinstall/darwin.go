//go:build darwin

package svcinstall

import (
	"fmt"
	"os"
	"os/exec"
	"strings"
)

const (
	plistLabel = "com.securisti.aegis-ea"
	plistPath  = "/Library/LaunchDaemons/com.securisti.aegis-ea.plist"
)

// Install creates and loads a launchd plist for the agent.
func Install(configPath string) error {
	exe, err := selfExe()
	if err != nil {
		return err
	}

	plist := strings.Join([]string{
		`<?xml version="1.0" encoding="UTF-8"?>`,
		`<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"`,
		`  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">`,
		`<plist version="1.0">`,
		`<dict>`,
		`  <key>Label</key>`,
		`  <string>` + plistLabel + `</string>`,
		`  <key>ProgramArguments</key>`,
		`  <array>`,
		`    <string>` + exe + `</string>`,
		`    <string>--config</string>`,
		`    <string>` + configPath + `</string>`,
		`  </array>`,
		`  <key>RunAtLoad</key>`,
		`  <true/>`,
		`  <key>KeepAlive</key>`,
		`  <dict>`,
		`    <key>SuccessfulExit</key>`,
		`    <false/>`,
		`  </dict>`,
		`  <key>ThrottleInterval</key>`,
		`  <integer>10</integer>`,
		`  <key>StandardOutPath</key>`,
		`  <string>/var/log/aegis-ea.log</string>`,
		`  <key>StandardErrorPath</key>`,
		`  <string>/var/log/aegis-ea.log</string>`,
		`  <key>ProcessType</key>`,
		`  <string>Background</string>`,
		`</dict>`,
		`</plist>`,
	}, "\n")

	if err := os.WriteFile(plistPath, []byte(plist+"\n"), 0644); err != nil {
		return fmt.Errorf("write plist: %w", err)
	}

	// Unload first (idempotent — ignore error if not loaded).
	_, _ = exec.Command("launchctl", "unload", plistPath).CombinedOutput()

	out, err := exec.Command("launchctl", "load", "-w", plistPath).CombinedOutput()
	if err != nil {
		return fmt.Errorf("launchctl load: %w\n%s", err, out)
	}
	fmt.Printf("aegis-ea: installed launchd plist → %s\n", plistPath)
	fmt.Println("aegis-ea: daemon loaded and running")
	fmt.Println("aegis-ea: check status:  launchctl list | grep aegis")
	fmt.Println("aegis-ea: view logs:     tail -f /var/log/aegis-ea.log")
	return nil
}

// Uninstall stops and removes the launchd plist.
func Uninstall() error {
	_, _ = exec.Command("launchctl", "unload", "-w", plistPath).CombinedOutput()
	if err := os.Remove(plistPath); err != nil && !os.IsNotExist(err) {
		return fmt.Errorf("remove plist: %w", err)
	}
	fmt.Println("aegis-ea: launchd plist removed")
	return nil
}
