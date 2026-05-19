//go:build !linux && !darwin && !windows

package netmon

// platformSnapshot stub for unsupported OSes — keeps `go vet ./...`
// green on any dev host.
func platformSnapshot() ([]Conn, map[int]string, error) {
	return nil, nil, nil
}
