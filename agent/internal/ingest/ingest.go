// Package ingest — HTTPS event batching client.
//
// Sends batches to /v1/ingest/endpoint-agent with `Authorization: Bearer
// <agent_token>`. On 4xx the batch is dropped (the backend told us it's
// malformed); on 5xx / network error the batch is held for up to one
// retry with exponential backoff. Steady-state failure is logged and
// metered via the heartbeat overflow counter.
package ingest

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"time"

	"github.com/securisti/aegis-endpoint-agent/internal/events"
)

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

// Flush sends `evts` in a single batch. Empty input is a no-op.
func (c *Client) Flush(ctx context.Context, evts []events.Event) error {
	if len(evts) == 0 {
		return nil
	}
	body, err := json.Marshal(batch{DeviceID: c.DeviceID, Events: evts})
	if err != nil {
		return err
	}
	// Two-attempt retry with 1-second backoff. Beyond that the batch
	// is dropped; in v1 the agent does not persist events to disk.
	var lastErr error
	for attempt := 0; attempt < 2; attempt++ {
		if attempt > 0 {
			select {
			case <-ctx.Done():
				return ctx.Err()
			case <-time.After(time.Second):
			}
		}
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.URL, bytes.NewReader(body))
		if err != nil {
			return err
		}
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Authorization", "Bearer "+c.Token)
		resp, err := c.http.Do(req)
		if err != nil {
			lastErr = err
			continue
		}
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		resp.Body.Close()
		switch {
		case resp.StatusCode >= 200 && resp.StatusCode < 300:
			return nil
		case resp.StatusCode == http.StatusUnauthorized,
			resp.StatusCode == http.StatusForbidden:
			// Token revoked or device removed — there's no recovery
			// possible without re-enrolment. Surface the error.
			return fmt.Errorf("ingest auth failure (%d): %s", resp.StatusCode, string(raw))
		case resp.StatusCode >= 400 && resp.StatusCode < 500:
			// Malformed batch (e.g. PII-shaped key). Drop it; the
			// backend already logged the offending key.
			return fmt.Errorf("ingest 4xx (%d): %s", resp.StatusCode, string(raw))
		default:
			lastErr = fmt.Errorf("ingest 5xx (%d): %s", resp.StatusCode, string(raw))
		}
	}
	if lastErr == nil {
		lastErr = errors.New("ingest failed for unknown reason")
	}
	return lastErr
}
