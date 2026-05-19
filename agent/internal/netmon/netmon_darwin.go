//go:build darwin

package netmon

import (
	"bytes"
	"context"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

// platformSnapshot uses `lsof -nP -iTCP -sTCP:ESTABLISHED -F pcLn`
// for a structured listing.
//
// -F p   PID
// -F c   command (process name)
// -F n   name (in -i mode this is the connection endpoint)
// -F L   login (skipped here)
//
// Output is line-prefixed by field code. No admin required to list
// the user's own connections; system-wide visibility needs the
// `procmod` and `system.privilege.taskport.safe` entitlements which
// the EndpointSecurity back-end will request post-GA.
func platformSnapshot() ([]Conn, map[int]string, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "/usr/sbin/lsof",
		"-nP", "-iTCP", "-sTCP:ESTABLISHED", "-FpcLn")
	var out bytes.Buffer
	cmd.Stdout = &out
	// lsof can exit non-zero when some sockets aren't readable — that's
	// fine, we still parse what we got.
	_ = cmd.Run()

	conns := []Conn{}
	pidToName := map[int]string{}

	var curPID int
	var curName string
	for _, line := range strings.Split(out.String(), "\n") {
		if line == "" {
			continue
		}
		code := line[0]
		val := line[1:]
		switch code {
		case 'p':
			pid, err := strconv.Atoi(val)
			if err == nil {
				curPID = pid
			}
		case 'c':
			curName = strings.ToLower(val)
			pidToName[curPID] = curName
		case 'n':
			// Format: "1.2.3.4:54321->5.6.7.8:443"
			arrow := strings.Index(val, "->")
			if arrow < 0 {
				continue
			}
			right := val[arrow+2:]
			if colon := strings.LastIndex(right, ":"); colon > 0 {
				ip := right[:colon]
				ip = strings.TrimPrefix(strings.TrimSuffix(ip, "]"), "[")
				conns = append(conns, Conn{PID: curPID, RemoteIP: ip})
			}
		}
	}
	return conns, pidToName, nil
}
