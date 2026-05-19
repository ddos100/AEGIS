//go:build !linux && !darwin && !windows

package procmon

// platformSnapshot stub for unsupported OSes — keeps `go vet ./...`
// green on any dev host while the supported builds use the real impls.
func platformSnapshot() ([]Proc, error) { return nil, nil }
