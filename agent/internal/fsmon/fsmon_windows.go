//go:build windows

package fsmon

// overriddenNew is the Windows back-end hook. The real implementation
// will wire ETW providers Microsoft-Windows-Kernel-Process and
// Microsoft-Windows-Kernel-File via golang.org/x/sys/windows/etw plus
// ETW kernel-file events for watched paths.
//
// v1 returns nil so `New()` falls through to the portable polling
// fallback.
func overriddenNew() Monitor { return nil }
