//go:build windows

package svcinstall

import (
	"fmt"
	"os/exec"
	"strings"
)

// Windows uses sc.exe — no CGo, no external dependencies, works on
// Server 2016+ / Windows 10+.  The agent runs as LOCAL SERVICE
// (limited privileges, network access only).
//
// We intentionally avoid golang.org/x/sys/windows/svc because it
// requires the binary to implement the full Service Control Handler,
// which changes the startup path for all three OSes.  Using sc.exe
// keeps the agent a plain foreground process everywhere; the Service
// Control Manager just starts/stops it and handles restarts.

// Install creates a Windows service via sc.exe and starts it.
func Install(configPath string) error {
	exe, err := selfExe()
	if err != nil {
		return err
	}

	binPath := fmt.Sprintf(`"%s" --config "%s"`, exe, configPath)

	// Delete first if exists (idempotent reinstall).
	_, _ = exec.Command("sc.exe", "stop", ServiceName).CombinedOutput()
	_, _ = exec.Command("sc.exe", "delete", ServiceName).CombinedOutput()

	// sc.exe uses a quirky syntax: each option is TWO argv tokens where
	// the first token ends with '=' and the second is the value.
	//   sc create svc binPath= "C:\foo.exe" start= auto obj= "NT AUTHORITY\LocalService"
	// Go's exec.Command passes each element as a discrete argv entry,
	// which is exactly what sc.exe expects.
	args := []string{
		"create", ServiceName,
		"binPath=", binPath,
		"DisplayName=", DisplayName,
		"start=", "auto",
		"obj=", "NT AUTHORITY\\LocalService",
	}
	out, err := exec.Command("sc.exe", args...).CombinedOutput()
	if err != nil {
		return fmt.Errorf("sc create: %w\n%s", err, out)
	}

	// Set description.
	_, _ = exec.Command("sc.exe", "description", ServiceName, Description).CombinedOutput()

	// Configure auto-restart on failure (restart after 10s, up to 3 times).
	_, _ = exec.Command("sc.exe", "failure", ServiceName,
		"reset=", "86400",
		"actions=", "restart/10000/restart/10000/restart/10000",
	).CombinedOutput()

	// Start the service.
	out, err = exec.Command("sc.exe", "start", ServiceName).CombinedOutput()
	if err != nil {
		// Not fatal — the service is created, just not running yet.
		fmt.Printf("aegis-ea: warning: sc start: %s\n", strings.TrimSpace(string(out)))
	}

	fmt.Println("aegis-ea: Windows service installed and started")
	fmt.Println("aegis-ea: check status:  sc query aegis-ea")
	fmt.Println("aegis-ea: view logs:     Get-WinEvent -LogName Application | Where-Object {$_.ProviderName -eq 'aegis-ea'}")
	return nil
}

// Uninstall stops and deletes the Windows service.
func Uninstall() error {
	_, _ = exec.Command("sc.exe", "stop", ServiceName).CombinedOutput()
	out, err := exec.Command("sc.exe", "delete", ServiceName).CombinedOutput()
	if err != nil {
		outStr := strings.TrimSpace(string(out))
		// "The specified service does not exist" is fine.
		if strings.Contains(outStr, "1060") {
			fmt.Println("aegis-ea: service was not installed")
			return nil
		}
		return fmt.Errorf("sc delete: %w\n%s", err, out)
	}
	fmt.Println("aegis-ea: Windows service removed")
	return nil
}
