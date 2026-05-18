//go:build !linux && !darwin && !windows

package fsmon

// overriddenNew on unsupported platforms — keeps the build green so
// developers can `go vet ./...` from any OS.
func overriddenNew() Monitor { return nil }
