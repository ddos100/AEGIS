//go:build windows

package procmon

import (
	"bytes"
	"context"
	"encoding/csv"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

// platformSnapshot on Windows uses tasklist's CSV output to enumerate
// every running process WITHOUT requiring admin AND without spawning
// PowerShell on every poll (PowerShell startup adds ~500ms per call
// which is unacceptable for a 5s tick).
//
//   tasklist /v /fo csv /nh
//
// gives PID + Image Name + Session + Memory + Status + User + CPU +
// Window Title. We don't get parent PID or command line from
// tasklist alone. For parent PID + command line we additionally run
// wmic ONCE every 30s (or use a lighter alternative when available).
//
// To avoid the wmic overhead on every tick, this implementation
// returns Proc rows with just PID + Name from tasklist; the procmon
// dispatcher tolerates an empty PPID + Command and applies its
// detection rules with whatever it has. Command-line-based detectors
// (destructive command, package install) will fire less reliably on
// Windows in v1; the Phase 7.7 ETW back-end fixes this.
//
// As a pragmatic improvement: if `wmic` is present (still ships on
// Win10/11 despite deprecation), we try it ONCE per snapshot to
// populate command-line. The wmic call is bounded to 2 seconds and
// failures fall back to tasklist alone.
func platformSnapshot() ([]Proc, error) {
	procs, err := tasklistSnapshot()
	if err != nil {
		return nil, err
	}
	wmicEnrich(procs) // best-effort; mutates Command + PPID where available
	return procs, nil
}

func tasklistSnapshot() ([]Proc, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx, "tasklist.exe", "/fo", "csv", "/nh")
	var out bytes.Buffer
	cmd.Stdout = &out
	if err := cmd.Run(); err != nil {
		return nil, err
	}
	r := csv.NewReader(bytes.NewReader(out.Bytes()))
	r.FieldsPerRecord = -1
	rows, err := r.ReadAll()
	if err != nil {
		return nil, err
	}
	procs := make([]Proc, 0, len(rows))
	for _, row := range rows {
		if len(row) < 2 {
			continue
		}
		name := strings.ToLower(strings.TrimSpace(row[0]))
		pid, err := strconv.Atoi(strings.TrimSpace(row[1]))
		if err != nil {
			continue
		}
		procs = append(procs, Proc{
			PID:  pid,
			Name: name,
			// PPID + Command filled by wmicEnrich when available.
		})
	}
	return procs, nil
}

// wmicEnrich attempts to populate PPID + Command on each Proc. Best-
// effort: if wmic is missing or slow, returns silently. Bounded to
// 2 seconds total.
func wmicEnrich(procs []Proc) {
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	// `wmic process get ProcessId,ParentProcessId,CommandLine /format:csv`
	// emits a CSV with header `Node,CommandLine,ParentProcessId,ProcessId`.
	cmd := exec.CommandContext(ctx, "wmic.exe", "process", "get",
		"ProcessId,ParentProcessId,CommandLine", "/format:csv")
	var out bytes.Buffer
	cmd.Stdout = &out
	if err := cmd.Run(); err != nil {
		return
	}
	// wmic emits CRLF and a leading blank line; tolerate both.
	lines := strings.Split(out.String(), "\n")
	if len(lines) < 2 {
		return
	}
	// Find header row to identify column positions (wmic column
	// order is documented but Windows builds occasionally deviate).
	var idxCmd, idxPPID, idxPID = -1, -1, -1
	r := csv.NewReader(strings.NewReader(out.String()))
	r.FieldsPerRecord = -1
	rows, err := r.ReadAll()
	if err != nil {
		return
	}
	for _, row := range rows {
		if idxCmd < 0 {
			// Header row.
			for i, h := range row {
				switch strings.TrimSpace(h) {
				case "CommandLine":
					idxCmd = i
				case "ParentProcessId":
					idxPPID = i
				case "ProcessId":
					idxPID = i
				}
			}
			if idxPID < 0 {
				return
			}
			continue
		}
		if idxPID >= len(row) {
			continue
		}
		pid, err := strconv.Atoi(strings.TrimSpace(row[idxPID]))
		if err != nil {
			continue
		}
		var cmdStr string
		var ppid int
		if idxCmd >= 0 && idxCmd < len(row) {
			cmdStr = row[idxCmd]
		}
		if idxPPID >= 0 && idxPPID < len(row) {
			ppid, _ = strconv.Atoi(strings.TrimSpace(row[idxPPID]))
		}
		for i := range procs {
			if procs[i].PID == pid {
				procs[i].PPID = ppid
				procs[i].Command = cmdStr
				break
			}
		}
	}
}
