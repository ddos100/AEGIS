// Package ingest — HTTPS event batching client.
//
// Sends batches to /v1/ingest/endpoint-agent with
// `Authorization: Bearer <agent_token>`. Errors are typed so the
// agent's main loop can react sensibly:
//
//   ErrFatalAuth         401 / 403 — token revoked or device deleted.
//                         The agent CANNOT recover without re-enrolling
//                         with a fresh code; main() exits cleanly with
//                         a helpful message rather than looping forever.
//   ErrSchemaMismatch    422 — server rejects an event kind in the
//                         batch. Usually means the API container hasn't
//                         picked up the latest migration yet. The
//                         agent retries the batch with the offending
//                         kinds dropped so the rest still gets
//                         through (heartbeats stay alive).
//   (transient)          5xx / network — held for one 1-second retry
//                         then surfaced; main() logs and continues.
package ingest

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"time"

	"github.com/securisti/aegis-endpoint-agent/internal/events"
)

// Sentinel errors so callers can `errors.Is(...)`.
var (
	ErrFatalAuth      = errors.New("ingest auth failure")
	ErrSchemaMismatch = errors.New("ingest schema mismatch")
)

// AuthError carries the upstream HTTP status + body for logging.
type AuthError struct {
	StatusCode int
	Body       string
}

func (e *AuthError) Error() string {
	return fmt.Sprintf("ingest auth failure (%d): %s", e.StatusCode, e.Body)
}
func (e *AuthError) Unwrap() error { return ErrFatalAuth }

// SchemaError carries the upstream body so we can parse the offending
// kind out of it for partial-batch retry.
type SchemaError struct {
	StatusCode    int
	Body          string
	OffendingKind string // best-effort parse of the Pydantic error
}

func (e *SchemaError) Error() string {
	return fmt.Sprintf("ingest schema mismatch (%d): %s", e.StatusCode, e.Body)
}
func (e *SchemaError) Unwrap() error { return ErrSchemaMismatch }

type Client struct {
	URL      string
	Token    string
	DeviceID string
	http     *http.Client
}

func NewClient(url, token, deviceID string) *Client {
	return &Client{
		URL: url, Token: token, DeviceID: deviceID,
		http: &http.Client{Timeout: 30 * time.Second},
	}
}

type batch struct {
	DeviceID string         `json:"device_id"`
	Events   []events.Event `json:"events"`
}

// Pydantic's 422 error body for a Literal mismatch carries
// `"input":"<offending value>"` somewhere in the JSON. Extracting it
// regex-wise is faster + more robust than full JSON unmarshalling
// against an evolving error schema.
var pydanticInputRE = regexp.MustCompile(`"input"\s*:\s*"([^"]+)"`)

func parseOffendingKind(body string) string {
	m := pydanticInputRE.FindStringSubmatch(body)
	if len(m) >= 2 {
		return m[1]
	}
	return ""
}

// flushOnce sends one batch and returns (success?, err). The error is
// one of: nil, *AuthError, *SchemaError, transient.
func (c *Client) flushOnce(ctx context.Context, evts []events.Event) error {
	body, err := json.Marshal(batch{DeviceID: c.DeviceID, Events: evts})
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.URL, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+c.Token)
	resp, err := c.http.Do(req)
	if err != nil {
		return err
	}
	raw, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
	resp.Body.Close()
	switch {
	case resp.StatusCode >= 200 && resp.StatusCode < 300:
		return nil
	case resp.StatusCode == http.StatusUnauthorized,
		resp.StatusCode == http.StatusForbidden:
		return &AuthError{StatusCode: resp.StatusCode, Body: string(raw)}
	case resp.StatusCode == http.StatusUnprocessableEntity:
		return &SchemaError{
			StatusCode:    resp.StatusCode,
			Body:          string(raw),
			OffendingKind: parseOffendingKind(string(raw)),
		}
	case resp.StatusCode >= 400 && resp.StatusCode < 500:
		// Other 4xx — malformed batch the backend logged. Drop the
		// batch; nothing the agent can do.
		return fmt.Errorf("ingest 4xx (%d): %s", resp.StatusCode, string(raw))
	default:
		return fmt.Errorf("ingest 5xx (%d): %s", resp.StatusCode, string(raw))
	}
}

// Flush sends `evts` in a single batch with structured error handling:
//
//   * 5xx / network: one 1-second retry, then surface.
//   * 401/403: surface as *AuthError immediately (no point retrying).
//   * 422: surface as *SchemaError immediately AFTER attempting one
//          partial-batch retry with the offending kind dropped, so a
//          schema-skewed server still accepts the rest of the events
//          (the agent stays healthy and useful instead of dropping
//          everything).
//   * 2xx: nil.
func (c *Client) Flush(ctx context.Context, evts []events.Event) error {
	if len(evts) == 0 {
		return nil
	}

	// Up to two attempts for transient errors.
	var lastErr error
	for attempt := 0; attempt < 2; attempt++ {
		if attempt > 0 {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(time.Second):
			}
		}

		err := c.flushOnce(ctx, evts)
		if err == nil {
			return nil
		}

		// Auth failure — there's no recovery without re-enrolment.
		if ae, ok := err.(*AuthError); ok {
			return ae
		}

		// Schema mismatch — try once more with the offending kind
		// dropped from the batch. If the offending kind can't be
		// identified, surface the error so the operator sees the
		// upstream message.
		if se, ok := err.(*SchemaError); ok {
			if se.OffendingKind == "" {
				return se
			}
			filtered := make([]events.Event, 0, len(evts))
			for _, e := range evts {
				if e.Kind != se.OffendingKind {
					filtered = append(filtered, e)
				}
			}
			if len(filtered) == 0 {
				// Whole batch was the offending kind.
				return se
			}
			if err := c.flushOnce(ctx, filtered); err != nil {
				// Wrap so caller sees BOTH that schema drift happened
				// AND that the retry didn't fully succeed.
				return fmt.Errorf("schema drift: dropped %d %q events; retry: %w",
					len(evts)-len(filtered), se.OffendingKind, err)
			}
			return fmt.Errorf("schema drift: dropped %d %q events; backend "+
				"older than agent? run `alembic upgrade head` + restart api: %w",
				len(evts)-len(filtered), se.OffendingKind, ErrSchemaMismatch)
		}

		lastErr = err
		// Other 4xx already returned above; reach here only for 5xx /
		// network. Retry on next iteration.
	}
	if lastErr == nil {
		lastErr = errors.New("ingest failed for unknown reason")
	}
	return lastErr
}
