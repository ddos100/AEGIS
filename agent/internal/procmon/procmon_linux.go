//go:build linux

package procmon

import (
	"os"
	"strconv"
	"strings"
)

// platformSnapshot reads /proc to enumerate processes. No exec spawned;
// no admin required.
func platformSnapshot() ([]Proc, error) {
	entries, err := os.ReadDir("/proc")
	if err != nil {
		return nil, err
	}
	out := make([]Proc, 0, len(entries))
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		pid, err := strconv.Atoi(e.Name())
		if err != nil {
			continue
		}
		// Read /proc/<pid>/comm for the binary basename — bounded
		// to TASK_COMM_LEN (16 bytes).
		commBytes, err := os.ReadFile("/proc/" + e.Name() + "/comm")
		if err != nil {
			continue // process gone between Readdir and ReadFile
		}
		name := strings.TrimSpace(string(commBytes))

		// /proc/<pid>/cmdline — NUL-separated argv. May be empty for
		// kernel threads; skip those.
		cmdBytes, err := os.ReadFile("/proc/" + e.Name() + "/cmdline")
		if err != nil || len(cmdBytes) == 0 {
			continue
		}
		cmdline := strings.ReplaceAll(strings.TrimRight(string(cmdBytes), "\x00"), "\x00", " ")

		// /proc/<pid>/status — extract PPid for parent-PID correlation.
		ppid := 0
		if statBytes, err := os.ReadFile("/proc/" + e.Name() + "/status"); err == nil {
			for _, line := range strings.Split(string(statBytes), "\n") {
				if strings.HasPrefix(line, "PPid:") {
					if v, err := strconv.Atoi(strings.TrimSpace(strings.TrimPrefix(line, "PPid:"))); err == nil {
						ppid = v
					}
					break
				}
			}
		}

		out = append(out, Proc{
			PID:     pid,
			PPID:    ppid,
			Name:    strings.ToLower(name),
			Command: cmdline,
		})
	}
	return out, nil
}
