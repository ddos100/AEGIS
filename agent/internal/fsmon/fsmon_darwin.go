//go:build darwin

package fsmon

// overriddenNew is the macOS back-end hook. The real implementation
// will wire EndpointSecurity (es_new_client + ES_EVENT_TYPE_NOTIFY_*)
// with the AEGIS Apple Developer ID entitlement. Falls back to
// FSEvents-only when the entitlement is absent (a banner in the UI
// surfaces the reduced-visibility mode).
//
// v1 returns nil so `New()` falls through to the portable polling
// fallback.
func overriddenNew() Monitor { return nil }
