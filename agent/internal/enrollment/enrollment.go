// Package enrollment — first-run bootstrap that exchanges a one-time
// enrollment code (minted by an AEGIS admin) for a device-scoped
// signed token.
package enrollment

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"
)

type request struct {
	EnrollmentCode string `json:"enrollment_code"`
	Hostname       string `json:"hostname"`
	OS             string `json:"os"`
	Arch           string `json:"arch"`
	AgentVersion   string `json:"agent_version"`
}

type response struct {
	DeviceID         string `json:"device_id"`
	AgentToken       string `json:"agent_token"`
	IngestURL        string `json:"ingest_url"`
	HeartbeatSeconds int    `json:"heartbeat_seconds"`
}

// Enroll posts the request and returns (token, deviceID, ingestURL, err).
func Enroll(apiURL, code, hostname, osName, arch, agentVersion string) (string, string, string, error) {
	u, err := url.JoinPath(apiURL, "/v1/endpoint-agent/enroll")
	if err != nil {
		return "", "", "", fmt.Errorf("build url: %w", err)
	}
	body, _ := json.Marshal(request{
		EnrollmentCode: code, Hostname: hostname,
		OS: osName, Arch: arch, AgentVersion: agentVersion,
	})
	client := &http.Client{Timeout: 30 * time.Second}
	req, _ := http.NewRequest(http.MethodPost, u, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := client.Do(req)
	if err != nil {
		return "", "", "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		raw, _ := io.ReadAll(io.LimitReader(resp.Body, 4096))
		return "", "", "", fmt.Errorf("enroll failed (%d): %s", resp.StatusCode, string(raw))
	}
	var r response
	if err := json.NewDecoder(resp.Body).Decode(&r); err != nil {
		return "", "", "", err
	}
	if r.AgentToken == "" || r.DeviceID == "" {
		return "", "", "", errors.New("enrollment response missing token or device_id")
	}
	// If the backend returned a relative ingest path, join it onto the
	// configured API URL so the agent has an absolute target.
	ingestURL := r.IngestURL
	if ingestURL == "" || ingestURL[0] == '/' {
		joined, err := url.JoinPath(apiURL, ingestURL)
		if err == nil {
			ingestURL = joined
		}
	}
	return r.AgentToken, r.DeviceID, ingestURL, nil
}
