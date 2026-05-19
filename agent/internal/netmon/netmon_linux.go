//go:build linux

package netmon

import (
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// platformSnapshot reads /proc/net/{tcp,tcp6} for the TCP table, then
// walks /proc/<pid>/fd to map socket inodes back to PIDs. No exec.
func platformSnapshot() ([]Conn, map[int]string, error) {
	socketInode2Remote := map[string]string{} // inode -> remote IP

	for _, p := range []string{"/proc/net/tcp", "/proc/net/tcp6"} {
		raw, err := os.ReadFile(p)
		if err != nil {
			continue
		}
		isV6 := strings.HasSuffix(p, "tcp6")
		// Skip header line.
		for _, line := range strings.Split(string(raw), "\n")[1:] {
			f := strings.Fields(line)
			if len(f) < 10 {
				continue
			}
			// State 01 = ESTABLISHED. We only care about live conns.
			if f[3] != "01" {
				continue
			}
			ip, ok := parseProcAddr(f[2], isV6)
			if !ok {
				continue
			}
			inode := f[9]
			if inode == "0" {
				continue
			}
			socketInode2Remote[inode] = ip
		}
	}

	pidToName := map[int]string{}
	conns := []Conn{}

	entries, err := os.ReadDir("/proc")
	if err != nil {
		return nil, nil, err
	}
	for _, e := range entries {
		if !e.IsDir() {
			continue
		}
		pid, err := strconv.Atoi(e.Name())
		if err != nil {
			continue
		}
		fdDir := filepath.Join("/proc", e.Name(), "fd")
		fds, err := os.ReadDir(fdDir)
		if err != nil {
			continue
		}
		var matched []string
		for _, fd := range fds {
			target, err := os.Readlink(filepath.Join(fdDir, fd.Name()))
			if err != nil {
				continue
			}
			if !strings.HasPrefix(target, "socket:[") {
				continue
			}
			inode := strings.TrimSuffix(strings.TrimPrefix(target, "socket:["), "]")
			if ip, ok := socketInode2Remote[inode]; ok {
				matched = append(matched, ip)
			}
		}
		if len(matched) == 0 {
			continue
		}
		// Resolve process name.
		commBytes, err := os.ReadFile(filepath.Join("/proc", e.Name(), "comm"))
		if err != nil {
			continue
		}
		name := strings.ToLower(strings.TrimSpace(string(commBytes)))
		pidToName[pid] = name
		for _, ip := range matched {
			conns = append(conns, Conn{PID: pid, RemoteIP: ip})
		}
	}
	return conns, pidToName, nil
}

// parseProcAddr decodes /proc/net/tcp's hex remote address column.
// Format: "C0A80001:01BB" → "192.168.0.1" (port 443) for IPv4,
// "00000000000000000000FFFFC0A80001:01BB" → "192.168.0.1" for IPv6
// when it's a v4-mapped address. We only return the IP.
func parseProcAddr(s string, isV6 bool) (string, bool) {
	colon := strings.IndexByte(s, ':')
	if colon < 0 {
		return "", false
	}
	hexIP := s[:colon]
	if isV6 {
		// 32 hex chars = 16 bytes. Linux stores the words little-endian
		// per 32-bit chunk.
		if len(hexIP) != 32 {
			return "", false
		}
		raw, err := hex.DecodeString(hexIP)
		if err != nil || len(raw) != 16 {
			return "", false
		}
		// Swap each 4-byte group's endianness.
		bs := make([]byte, 16)
		for i := 0; i < 16; i += 4 {
			bs[i] = raw[i+3]
			bs[i+1] = raw[i+2]
			bs[i+2] = raw[i+1]
			bs[i+3] = raw[i]
		}
		// v4-mapped check (::ffff:a.b.c.d)
		if bs[0] == 0 && bs[1] == 0 && bs[2] == 0 && bs[3] == 0 &&
			bs[4] == 0 && bs[5] == 0 && bs[6] == 0 && bs[7] == 0 &&
			bs[8] == 0 && bs[9] == 0 && bs[10] == 0xff && bs[11] == 0xff {
			return fmt.Sprintf("%d.%d.%d.%d", bs[12], bs[13], bs[14], bs[15]), true
		}
		// Compact IPv6.
		return fmt.Sprintf("%x:%x:%x:%x:%x:%x:%x:%x",
			uint16(bs[0])<<8|uint16(bs[1]),
			uint16(bs[2])<<8|uint16(bs[3]),
			uint16(bs[4])<<8|uint16(bs[5]),
			uint16(bs[6])<<8|uint16(bs[7]),
			uint16(bs[8])<<8|uint16(bs[9]),
			uint16(bs[10])<<8|uint16(bs[11]),
			uint16(bs[12])<<8|uint16(bs[13]),
			uint16(bs[14])<<8|uint16(bs[15])), true
	}
	if len(hexIP) != 8 {
		return "", false
	}
	raw, err := hex.DecodeString(hexIP)
	if err != nil || len(raw) != 4 {
		return "", false
	}
	// /proc/net/tcp stores host-byte-order; on LE machines that means
	// the four bytes are reversed.
	return fmt.Sprintf("%d.%d.%d.%d", raw[3], raw[2], raw[1], raw[0]), true
}
