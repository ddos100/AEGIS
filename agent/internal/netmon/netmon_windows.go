//go:build windows

package netmon

import (
	"bytes"
	"context"
	"encoding/csv"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

// platformSnapshot on Windows uses two well-known commands that ship
// in every Windows install since Vista — no admin, no third-party
// dependency:
//
//   netstat -ano        Active TCP/UDP connections with PIDs
//   tasklist /fo csv    PID -> Image Name mapping
//
// Output is parsed and joined in-process. ETW providers give richer
// data (incl. parent PID + image hash) but require admin at install
// time; that path is the Phase 7.7 native back-end.
func platformSnapshot() ([]Conn, map[int]string, error) {
	pidToName, err := tasklistNames()
	if err != nil {
		return nil, nil, err
	}
	conns, err := netstatConnections()
	if err != nil {
		return nil, nil, err
	}
	return conns, pidToName, nil
}

func tasklistNames() (map[int]string, error) {
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
	m := map[int]string{}
	for _, row := range rows {
		if len(row) < 2 {
			continue
		}
		name := strings.ToLower(strings.TrimSpace(row[0]))
		pid, err := strconv.Atoi(strings.TrimSpace(row[1]))
		if err != nil {
			continue
		}
		m[pid] = name
	}
	return m, nil
}

func netstatConnections() ([]Conn, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	cmd := exec.CommandContext(ctx, "netstat.exe", "-ano")
	var out bytes.Buffer
	cmd.Stdout = &out
	if err := cmd.Run(); err != nil {
		return nil, err
	}
	conns := []Conn{}
	for _, line := range strings.Split(out.String(), "\n") {
		line = strings.TrimSpace(line)
		if !strings.HasPrefix(line, "TCP") {
			continue
		}
		f := strings.Fields(line)
		// Expected:  TCP  <local>  <remote>  <state>  <pid>
		if len(f) < 5 {
			continue
		}
		state := f[3]
		if !strings.EqualFold(state, "ESTABLISHED") {
			continue
		}
		pid, err := strconv.Atoi(f[4])
		if err != nil {
			continue
		}
		remote := f[2]
		// remote format:  1.2.3.4:443  or  [::1]:443
		ip := remote
		if strings.HasPrefix(remote, "[") {
			if cb := strings.Index(remote, "]"); cb > 0 {
				ip = remote[1:cb]
			}
		} else if colon := strings.LastIndex(remote, ":"); colon > 0 {
			ip = remote[:colon]
		}
		conns = append(conns, Conn{PID: pid, RemoteIP: ip})
	}
	return conns, nil
}
