//go:build linux

package fsmon

// overriddenNew is the Linux back-end hook. The real implementation
// will wire fanotify FAN_CLASS_NOTIF + FAN_REPORT_FID for the watched
// paths and a process-event netlink listener for the curl|sh /
// destructive-cmd detectors documented in PHASE-7-PLAN.md §B.3.4.
//
// v1 returns nil so `New()` falls through to the portable polling
// fallback. When this is implemented, return the fanotify-backed
// monitor here.
func overriddenNew() Monitor { return nil }
