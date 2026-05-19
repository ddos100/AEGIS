// Package netmon — cross-platform network connection poller.
//
// Resolves a list of known AI provider domains to IP addresses at
// startup (refreshed every 30 min) and polls the OS connection table
// every 15 s. For each active TCP connection whose remote address
// matches one of the resolved IPs, emits one `ai_provider_connection`
// event per (process, domain) pair per detection window.
//
// What this catches that other layers miss
//   * Cursor / Claude Desktop / VS Code AI extension calling
//     api.cursor.sh / api.anthropic.com / api.openai.com directly —
//     network proxies see this if traffic is forced through them, but
//     many corporate fleets have laptops on home WiFi during the
//     workday. Local netmon catches those.
//   * A python script using the openai SDK calling api.openai.com —
//     even without identifying it as a Python AI usage via process
//     name + SDK heuristic, the network connection is dispositive.
//   * AI desktop binaries that POST to vendor APIs without ever
//     touching watched files.
//
// Privacy contract
//   * Reports only (process_name, remote_domain) tuples.
//   * Never reports remote IP, remote port, local IP, local port,
//     URL path, or any payload. The backend allow-list rejects any
//     such fields.
//   * Domains are pattern-matched from a fixed allow-list of AI
//     provider domains — we don't dump every connection.
//
// Mechanism
//   Linux   /proc/net/{tcp,tcp6} + /proc/<pid>/fd/* socket inode join
//   macOS   `lsof -nP -i -F pcLn` (no admin)
//   Windows `netstat -ano` + tasklist for PID -> name
package netmon

import (
	"context"
	"net"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/securisti/aegis-endpoint-agent/internal/events"
)

// Conn is one row from a network snapshot.
type Conn struct {
	PID      int
	RemoteIP string // dotted-quad or IPv6 — never sent to backend
	// RemotePort and LocalIP/LocalPort intentionally omitted.
}

// Snapshot returns the current TCP connection table. Per-OS impls.
func Snapshot() ([]Conn, map[int]string, error) {
	return platformSnapshot()
}

// AI provider domain inventory. Same family as the catalogue
// `observed_provider_domains` predicate values.
var aiProviderDomains = []string{
	// OpenAI / ChatGPT
	"api.openai.com", "chat.openai.com", "chatgpt.com",
	"oaistatic.com",
	// Anthropic
	"api.anthropic.com", "claude.ai", "console.anthropic.com",
	// Google
	"generativelanguage.googleapis.com", "gemini.google.com",
	"aistudio.google.com", "bard.google.com",
	// Microsoft
	"copilot.microsoft.com", "bing.com/chat", "api.cognitive.microsoft.com",
	"openai.azure.com",
	// Meta / Mistral / xAI / Perplexity / Cohere
	"api.mistral.ai", "console.mistral.ai",
	"api.x.ai", "grok.com",
	"www.perplexity.ai", "api.perplexity.ai",
	"api.cohere.ai", "api.cohere.com",
	// Cursor / Claude Desktop / Cline / Continue / Codeium / Tabnine
	"api.cursor.sh", "api.cursor.com",
	"api.cline.bot",
	"api.continue.dev",
	"server.codeium.com", "inference.codeium.com",
	"api.tabnine.com",
	// HuggingFace / Replicate / Together / Fireworks / Groq
	"huggingface.co", "api-inference.huggingface.co",
	"api.replicate.com", "replicate.delivery",
	"api.together.xyz",
	"api.fireworks.ai",
	"api.groq.com",
	// Browser AI extensions
	"monica.im", "sider.ai", "getmerlin.in", "maxai.me", "harpa.ai",
	// AI deepfake / image / video studios
	"d-id.com", "studio.d-id.com",
	"heygen.com", "elevenlabs.io",
	"synthesia.io",
	"runwayml.com", "pika.art", "lumalabs.ai",
	// Otter / Fireflies / Fathom / Gong
	"otter.ai", "fireflies.ai", "fathom.video", "gong.io",
	// Local model proxies that might be reached over network
	"ollama.ai",
}

// resolvedDomains maps an IPv4/IPv6 string back to the domain it
// belongs to. We resolve each provider name with net.LookupHost at
// startup and refresh every 30 min — IPs change but slowly enough
// for this cadence.
type resolver struct {
	mu       sync.RWMutex
	ipToHost map[string]string
}

func (r *resolver) refresh() {
	next := map[string]string{}
	for _, host := range aiProviderDomains {
		addrs, err := net.LookupHost(host)
		if err != nil {
			continue
		}
		for _, a := range addrs {
			next[a] = host
		}
	}
	r.mu.Lock()
	r.ipToHost = next
	r.mu.Unlock()
}

func (r *resolver) hostFor(ip string) (string, bool) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	h, ok := r.ipToHost[ip]
	return h, ok
}

// Monitor drives the netmon poll loop.
type Monitor struct {
	out      chan events.Event
	resolver *resolver

	mu        sync.Mutex
	seenPairs map[string]time.Time // "pid|domain" -> last emit
	cancel    context.CancelFunc
}

func New() *Monitor {
	return &Monitor{
		resolver:  &resolver{ipToHost: map[string]string{}},
		seenPairs: map[string]time.Time{},
	}
}

func (m *Monitor) Start(ctx context.Context) (<-chan events.Event, error) {
	subCtx, cancel := context.WithCancel(ctx)
	m.cancel = cancel
	m.out = make(chan events.Event, 128)
	m.resolver.refresh() // seed
	go m.loop(subCtx)
	return m.out, nil
}

func (m *Monitor) Stop() {
	if m.cancel != nil {
		m.cancel()
	}
}

func (m *Monitor) Name() string {
	dn := 0
	m.resolver.mu.RLock()
	dn = len(m.resolver.ipToHost)
	m.resolver.mu.RUnlock()
	return "netmon-poll (" + strings.Join(domainSampleLabels(dn), "") + ")"
}

func domainSampleLabels(n int) []string {
	// Compact: just the count to avoid leaking sample IPs into logs.
	return []string{itoa(n), " AI IPs"}
}

func itoa(i int) string {
	// Manual to avoid pulling strconv in this tiny helper.
	if i == 0 {
		return "0"
	}
	digits := []byte{}
	for i > 0 {
		digits = append([]byte{byte('0' + i%10)}, digits...)
		i /= 10
	}
	return string(digits)
}

// dedupWindow — emit the same (pid, domain) pair at most once per
// window so a long-lived connection doesn't generate a flood.
const dedupWindow = 5 * time.Minute

func (m *Monitor) loop(ctx context.Context) {
	defer close(m.out)
	refreshTicker := time.NewTicker(30 * time.Minute)
	defer refreshTicker.Stop()
	pollTicker := time.NewTicker(15 * time.Second)
	defer pollTicker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-refreshTicker.C:
			m.resolver.refresh()
		case <-pollTicker.C:
			m.tick()
		}
	}
}

func (m *Monitor) tick() {
	conns, pidToName, err := Snapshot()
	if err != nil {
		return
	}

	now := time.Now()
	m.mu.Lock()
	defer m.mu.Unlock()
	// Reap stale dedup entries.
	for k, t := range m.seenPairs {
		if now.Sub(t) > dedupWindow {
			delete(m.seenPairs, k)
		}
	}

	// Stable iteration so the first-PID for a shared IP is consistent.
	sort.Slice(conns, func(i, j int) bool {
		if conns[i].PID == conns[j].PID {
			return conns[i].RemoteIP < conns[j].RemoteIP
		}
		return conns[i].PID < conns[j].PID
	})

	for _, c := range conns {
		host, ok := m.resolver.hostFor(c.RemoteIP)
		if !ok {
			continue
		}
		name := strings.ToLower(pidToName[c.PID])
		key := keyOf(c.PID, host)
		if _, recently := m.seenPairs[key]; recently {
			continue
		}
		m.seenPairs[key] = now
		m.out <- events.AIProviderConnection(name, host)
	}
}

func keyOf(pid int, host string) string {
	return itoa(pid) + "|" + host
}
