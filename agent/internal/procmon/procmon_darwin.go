//go:build darwin

package procmon

import (
	"bytes"
	"context"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

// platformSnapshot exec's BSD `ps` with a stable column layout.
//   ps -axwwo pid=,ppid=,comm=,command=
// Each column trailing `=` suppresses the header.
//
// macOS ships `ps` in /bin/ps as standard; no admin required.
//
// We bound the exec to 3 seconds to avoid blocking the agent's poll
// loop if the OS is wedged.
func platformSnapshot() ([]Proc, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx, "/bin/ps", "-axwwo", "pid=,ppid=,comm=,command=")
	var out bytes.Buffer
	cmd.Stdout = &out
	if err := cmd.Run(); err != nil {
		return nil, err
	}

	procs := []Proc{}
	for _, line := range strings.Split(out.String(), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		// pid + ppid + comm + command — first three are
		// whitespace-separated; the rest is the command line.
		fields := strings.Fields(line)
		if len(fields) < 4 {
			continue
		}
		pid, err := strconv.Atoi(fields[0])
		if err != nil {
			continue
		}
		ppid, _ := strconv.Atoi(fields[1])
		comm := fields[2]
		// Rebuild the command line.
		joined := strings.Join(fields[3:], " ")
		// `comm` includes the full path on macOS; reduce to basename.
		name := comm
		if i := strings.LastIndex(comm, "/"); i >= 0 {
			name = comm[i+1:]
		}
		procs = append(procs, Proc{
			PID: pid, PPID: ppid,
			Name:    strings.ToLower(name),
			Command: joined,
		})
	}
	return procs, nil
}
