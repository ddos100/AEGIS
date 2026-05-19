import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import {
  useDiscoveryFeed,
  useDiscoveryStream,
  useDiscoveryVectors,
  useTestBroadcast,
  useTopSystems,
} from '@/hooks/useDiscovery';
import type { DiscoveryFeedItem, WSMessage } from '@/types/discovery';

/**
 * Project a WS `new_system` event into the shape REST returns.
 *
 * REST `/v1/discovery/feed` reads `ai_usage_events JOIN ai_systems`, so it
 * surfaces *individual telemetry events*. The WS stream emits one
 * notification per *newly auto-registered shadow system*. These are
 * semantically distinct sources, but operators reasonably expect the
 * "Recent events" panel to show everything that just happened — so we
 * merge the live notifications into the same render and tag them as
 * `source: 'live-ws'` for visibility.
 */
function wsToFeedItem(m: WSMessage): DiscoveryFeedItem | null {
  if (m.type !== 'new_system') return null;
  const p = m.payload;
  return {
    occurred_at:   p.first_discovered_at,
    catalogue_slug: p.catalogue_slug,
    ai_system_id:  p.id,
    name:          p.name,
    category:      p.category,
    vector:        p.vector,
    source:        'live-ws',
    user_email:    p.detected_by_user ?? null,
    department:    p.department ?? null,
    is_shadow:     true,
  };
}

function vectorIcon(vector: string) {
  // Compact ASCII glyphs (no emojis per house style).
  switch (vector) {
    case 'network_telemetry': return '⌁';
    case 'xdr_edr':           return '⊞';
    case 'browser_ext':       return '◫';
    case 'idp':               return '✱';
    case 'cloud':             return '☁';
    case 'saas':              return '⌘';
    case 'code_repo':         return '<>';
    default:                  return '·';
  }
}

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.max(1, Math.floor(ms / 1000));
  if (s < 60)   return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400)return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export default function DiscoveryPage() {
  const { messages, connected } = useDiscoveryStream(20);
  const { data: feed } = useDiscoveryFeed(24, 50);
  const { data: top } = useTopSystems(168, 10);
  const { data: vectors } = useDiscoveryVectors();
  const testBroadcast = useTestBroadcast();

  // Merge the REST feed with synthesized rows from the live WS stream so
  // the "Recent events" panel never looks empty while the radar is
  // actively receiving messages. De-dupe by ai_system_id so an event
  // that was first seen live and later landed in the REST poll appears
  // once.
  const mergedFeed: DiscoveryFeedItem[] = useMemo(() => {
    const fromWs = messages
      .map(wsToFeedItem)
      .filter((x): x is DiscoveryFeedItem => x !== null);
    const all = [...fromWs, ...(feed ?? [])];
    const seen = new Set<string>();
    const out: DiscoveryFeedItem[] = [];
    for (const row of all) {
      const key = `${row.ai_system_id ?? row.catalogue_slug ?? ''}|${row.occurred_at}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(row);
    }
    out.sort((a, b) => b.occurred_at.localeCompare(a.occurred_at));
    return out;
  }, [messages, feed]);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-brand-700">Discovery</h1>
          <p className="text-sm text-slate-600">
            Live shadow AI sightings across all enabled vectors —
            network proxies, NGFW/DNS logs, XDR/EDR telemetry, and the AEGIS browser extension.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => testBroadcast.mutate()}
            disabled={!connected || testBroadcast.isPending}
            title={connected ? 'Publish a synthetic event on this tenant’s discovery channel' : 'Connect the live feed first'}
            className="rounded-md border border-brand-500 px-3 py-1 text-xs font-medium text-brand-700 hover:bg-brand-50 disabled:opacity-50"
          >
            Test broadcast
          </button>
          <span className={connected ? 'badge-low' : 'badge bg-slate-100 text-slate-600'}>
            ● Live feed {connected ? 'connected' : 'reconnecting…'}
          </span>
        </div>
      </div>

      {!connected && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
          <b>Live feed not connected.</b> Common causes — not signed in
          (the rotating session token in <code>localStorage.aegis.session.v1</code> is empty),
          Vite proxy missing <code>ws:true</code> for <code>/v1/ws</code>, or the API not reachable on
          <code> /v1/ws/discovery</code>. The hook retries with exponential backoff (1s → 30s)
          and reconnects automatically on every silent session rotation. Recent events are still
          shown below via REST polling.
        </div>
      )}

      {/* Shadow AI Radar — live WebSocket feed */}
      <section className="rounded-lg border bg-white">
        <header className="flex items-center justify-between border-b px-4 py-2">
          <h2 className="font-semibold text-brand-700">Shadow AI Radar</h2>
          <span className="text-xs text-slate-500">{messages.length} live events</span>
        </header>
        <ul className="divide-y divide-slate-100 max-h-64 overflow-auto">
          {messages.length === 0 && (
            <li className="px-4 py-6 text-center text-sm text-slate-500">
              Waiting for new discovery events…
            </li>
          )}
          {messages.map((m, idx) => {
            if (m.type !== 'new_system') return null;
            const p = m.payload;
            return (
              <li key={idx} className="flex items-center gap-3 px-4 py-2">
                <span className="text-lg text-indigo-500">{vectorIcon(p.vector)}</span>
                <div className="flex-1">
                  <div className="text-sm">
                    <Link to={`/registry/${p.id}`} className="font-medium text-brand-700 hover:underline">
                      {p.name}
                    </Link>
                    <span className="ml-2 text-xs text-slate-500">via {p.vector}</span>
                    {p.detected_by_user && (
                      <span className="ml-2 text-xs text-slate-500">· user: {p.detected_by_user}</span>
                    )}
                  </div>
                  <div className="text-xs text-slate-400">{p.category} · {timeAgo(p.first_discovered_at)}</div>
                </div>
                <span className="badge-shadow">Shadow</span>
              </li>
            );
          })}
        </ul>
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Recent feed (REST + live merge) */}
        <section className="rounded-lg border bg-white">
          <header className="flex items-center justify-between border-b px-4 py-2">
            <h2 className="font-semibold text-brand-700">Recent events (24h)</h2>
            <span
              className="text-xs text-slate-500"
              title="Combined: REST poll of ai_usage_events + live WS notifications of newly-registered shadow systems"
            >
              {mergedFeed.length} · {feed?.length ?? 0} REST + {messages.length} live
            </span>
          </header>
          <ul className="divide-y divide-slate-100 max-h-96 overflow-auto">
            {mergedFeed.length === 0 && (
              <li className="px-4 py-6 text-center text-sm text-slate-500">
                {connected
                  ? 'Live feed connected, but nothing observed yet — neither in the ' +
                    'last 24h REST window nor on the WS stream. Try the test-broadcast ' +
                    'button or send a real ingest event.'
                  : 'No events ingested in the last 24h.'}
              </li>
            )}
            {mergedFeed.map((row, idx) => (
              <li key={`${row.ai_system_id ?? idx}|${row.occurred_at}`}
                  className="px-4 py-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-800">
                    {row.name || row.catalogue_slug || '(unknown)'}
                    {row.source === 'live-ws' && (
                      <span className="ml-2 rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] text-emerald-800">
                        live
                      </span>
                    )}
                  </span>
                  <span className="text-xs text-slate-500">{timeAgo(row.occurred_at)}</span>
                </div>
                <div className="text-xs text-slate-500">
                  {vectorIcon(row.vector)} {row.vector} · {row.source}
                  {row.user_email && <> · {row.user_email}</>}
                  {row.department && <> · {row.department}</>}
                </div>
              </li>
            ))}
          </ul>
        </section>

        {/* Top systems (last 7d) */}
        <section className="rounded-lg border bg-white">
          <header className="flex items-center justify-between border-b px-4 py-2">
            <h2 className="font-semibold text-brand-700">Top AI systems (7d)</h2>
          </header>
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2">System</th>
                <th className="px-4 py-2 text-right">Events</th>
                <th className="px-4 py-2 text-right">Users</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {top?.length === 0 && (
                <tr><td colSpan={3} className="px-4 py-6 text-center text-slate-500">No usage yet.</td></tr>
              )}
              {top?.map((s) => (
                <tr key={s.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2">
                    <Link to={`/registry/${s.id}`} className="font-medium text-brand-700 hover:underline">
                      {s.name}
                    </Link>
                    {s.is_shadow && <span className="ml-2 badge-shadow">Shadow</span>}
                    <div className="text-xs text-slate-500">{s.category}</div>
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">{s.event_count.toLocaleString()}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{s.unique_users}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      {/* Configured discovery vectors */}
      <section className="rounded-lg border bg-white">
        <header className="flex items-center justify-between border-b px-4 py-2">
          <h2 className="font-semibold text-brand-700">Configured vectors</h2>
          <span className="text-xs text-slate-500">{vectors?.length ?? 0}</span>
        </header>
        {vectors && vectors.length === 0 && (
          <div className="px-4 py-6 text-center text-sm text-slate-500">
            No discovery vectors configured yet — POST to <code>/v1/discovery/vectors</code> or
            send logs directly to <code>/v1/ingest/network</code>.
          </div>
        )}
        {vectors && vectors.length > 0 && (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2">Source</th>
                <th className="px-4 py-2">Type</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2 text-right">Events</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {vectors.map((v) => (
                <tr key={v.id}>
                  <td className="px-4 py-2">{v.name}</td>
                  <td className="px-4 py-2 text-slate-600">{v.source}</td>
                  <td className="px-4 py-2 text-slate-600">{v.vector_type}</td>
                  <td className="px-4 py-2">
                    <span className={v.status === 'active' ? 'badge-low' : 'badge bg-slate-100 text-slate-600'}>
                      {v.status}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums">{v.events_total.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
