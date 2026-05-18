import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  mintEnrollmentCode,
  revokeDevice,
  useDevices,
  useEAEvents,
  type EndpointDevice,
  type EnrollmentCode,
} from '@/hooks/useThreats';

const KIND_LABEL: Record<string, string> = {
  process_exec:                 'Process exec',
  file_write_to_watched_path:   'File write',
  secret_read_by_ai_proc:       'Secret read by AI proc',
  curl_pipe_sh_detected:        'curl | sh detected',
  mcp_config_observed:          'MCP config observed',
  package_install_pre_hook:     'Package install hook',
  path_shadow_detected:         'PATH shadow',
  autostart_artifact:           'Autostart artifact',
  heartbeat:                    'Heartbeat',
};

function osBadge(os: EndpointDevice['os']) {
  const cls = os === 'linux' ? 'bg-amber-100 text-amber-800'
            : os === 'darwin' ? 'bg-slate-200 text-slate-800'
            : 'bg-blue-100 text-blue-800';
  return <span className={`badge ${cls}`}>{os}</span>;
}

function deviceHealth(d: EndpointDevice): 'healthy' | 'stale' | 'revoked' | 'never' {
  if (d.revoked_at) return 'revoked';
  if (!d.last_heartbeat_at) return 'never';
  const last = new Date(d.last_heartbeat_at).getTime();
  return Date.now() - last < 5 * 60_000 ? 'healthy' : 'stale';
}

export default function EndpointAgentPage() {
  const { data: devices, isLoading, isError, error } = useDevices();
  const { data: events } = useEAEvents({ limit: 100 });
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [latestCode, setLatestCode] = useState<EnrollmentCode | null>(null);

  const notLicensed = (error as { response?: { status?: number } })?.response?.status === 402;

  const onMint = async () => {
    setBusy('mint');
    try {
      const c = await mintEnrollmentCode();
      setLatestCode(c);
    } finally { setBusy(null); }
  };

  const onRevoke = async (id: string) => {
    if (!window.confirm('Revoke this device? The agent will be rejected on next ingest.')) return;
    setBusy(id);
    try {
      await revokeDevice(id);
      qc.invalidateQueries({ queryKey: ['ea'] });
    } finally { setBusy(null); }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-brand-700">Endpoint Agents</h1>
          <p className="mt-1 max-w-3xl text-sm text-slate-600">
            AEGIS Endpoint Agent fleet. Each device observes a small allow-list of AI-tool
            paths and emits privacy-bounded events (no prompt text, no command-line plaintext,
            no file contents) to populate the <code>endpoint_agent_*</code> threat exposure
            predicates.
          </p>
        </div>
        <button
          onClick={onMint}
          disabled={busy === 'mint'}
          className="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {busy === 'mint' ? 'Generating…' : 'Generate enrolment code'}
        </button>
      </div>

      {notLicensed && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <code>AEGIS-EA</code> not licensed. Contact licensing@securisti.com.
        </div>
      )}

      {latestCode && (
        <section className="rounded-md border border-emerald-300 bg-emerald-50 p-4 text-sm text-emerald-900">
          <header className="font-medium">New enrolment code (single-use, expires 15 min)</header>
          <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded border bg-white p-3 font-mono text-xs">
{`aegis-ea --api-url ${window.location.origin} \\
         --enroll ${latestCode.enrollment_code}`}
          </pre>
          <p className="mt-2 text-xs">
            Expires {new Date(latestCode.expires_at).toLocaleString()} ·
            ingest at <code>{latestCode.ingest_url}</code>
          </p>
        </section>
      )}

      {devices && (
        <div className="grid gap-3 md:grid-cols-3">
          <div className="rounded-lg border bg-white p-4">
            <div className="text-xs text-slate-500">Enrolled devices</div>
            <div className="mt-1 text-3xl font-bold tabular-nums">{devices.total}</div>
          </div>
          <div className="rounded-lg border bg-white p-4">
            <div className="text-xs text-slate-500">Healthy (heartbeat &lt; 5m)</div>
            <div className="mt-1 text-3xl font-bold tabular-nums text-emerald-700">{devices.healthy}</div>
          </div>
          <div className="rounded-lg border bg-white p-4">
            <div className="text-xs text-slate-500">Events captured</div>
            <div className="mt-1 text-3xl font-bold tabular-nums">{events?.total ?? '—'}</div>
          </div>
        </div>
      )}

      {isLoading && <div className="text-sm text-slate-500">Loading…</div>}

      {devices && devices.items.length === 0 && (
        <div className="rounded-lg border border-dashed bg-white p-12 text-center text-slate-500">
          <div className="font-medium">No devices enrolled yet</div>
          <p className="mt-1 text-sm">
            Generate an enrolment code above and run the agent on a workstation:
            <code className="ml-1 rounded bg-slate-100 px-1">aegis-ea --enroll &lt;code&gt;</code>
          </p>
        </div>
      )}

      {devices && devices.items.length > 0 && (
        <section className="overflow-hidden rounded-lg border bg-white">
          <header className="border-b px-4 py-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            Fleet
          </header>
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2">Hostname</th>
                <th className="px-4 py-2 w-24">OS</th>
                <th className="px-4 py-2 w-32">Version</th>
                <th className="px-4 py-2 w-32">Status</th>
                <th className="px-4 py-2 w-44">Last heartbeat</th>
                <th className="px-4 py-2 w-32 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {devices.items.map((d) => {
                const h = deviceHealth(d);
                const badge = h === 'healthy' ? 'badge-low'
                            : h === 'stale'   ? 'badge-medium'
                            : h === 'revoked' ? 'badge-critical'
                            : 'badge bg-slate-100 text-slate-600';
                return (
                  <tr key={d.id} className="hover:bg-slate-50">
                    <td className="px-4 py-2 align-top font-medium text-slate-800">{d.hostname}</td>
                    <td className="px-4 py-2 align-top">{osBadge(d.os)} <span className="ml-1 text-xs text-slate-500">{d.arch}</span></td>
                    <td className="px-4 py-2 align-top font-mono text-xs">{d.agent_version}</td>
                    <td className="px-4 py-2 align-top"><span className={badge}>{h}</span></td>
                    <td className="px-4 py-2 align-top text-xs text-slate-500">
                      {d.last_heartbeat_at ? new Date(d.last_heartbeat_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-2 align-top text-right">
                      {!d.revoked_at && (
                        <button
                          disabled={busy === d.id}
                          onClick={() => onRevoke(d.id)}
                          className="rounded border border-red-300 bg-white px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-50"
                        >
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}

      {events && events.items.length > 0 && (
        <section className="overflow-hidden rounded-lg border bg-white">
          <header className="border-b px-4 py-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            Recent events (last 100)
          </header>
          <div className="flex flex-wrap gap-1 border-b bg-slate-50 px-4 py-2 text-xs">
            {Object.entries(events.by_kind).map(([k, n]) => (
              <span key={k} className="rounded-full bg-white px-2 py-0.5 text-slate-700">
                {KIND_LABEL[k] ?? k}: <b className="tabular-nums">{n}</b>
              </span>
            ))}
          </div>
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2 w-44">Kind</th>
                <th className="px-4 py-2">Hostname</th>
                <th className="px-4 py-2">Payload</th>
                <th className="px-4 py-2 w-44">Occurred</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {events.items.map((e) => (
                <tr key={e.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2 align-top">
                    <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-brand-700">{e.kind}</code>
                  </td>
                  <td className="px-4 py-2 align-top text-xs text-slate-700">{e.hostname ?? '—'}</td>
                  <td className="px-4 py-2 align-top">
                    <pre className="overflow-x-auto rounded bg-slate-50 p-1 text-[11px] text-slate-700">
                      {JSON.stringify(e.payload, null, 2)}
                    </pre>
                  </td>
                  <td className="px-4 py-2 align-top text-xs text-slate-500">
                    {new Date(e.occurred_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {isError && !notLicensed && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          Failed to load endpoint agents: {(error as Error).message}
        </div>
      )}
    </div>
  );
}
