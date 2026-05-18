import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  recomputeExposures,
  useExposures,
  type ExposureBrief,
  type ExposureStatus,
} from '@/hooks/useThreats';

const STATUS_LABEL: Record<ExposureStatus, { label: string; cls: string }> = {
  exposed:     { label: 'Exposed',      cls: 'badge-critical' },
  unknown:     { label: 'Unknown',      cls: 'badge-medium' },
  not_exposed: { label: 'Not exposed',  cls: 'badge-low' },
  mitigated:   { label: 'Mitigated',    cls: 'badge bg-emerald-100 text-emerald-800' },
};

function sevBadge(s: ExposureBrief['threat_severity']) {
  return s === 'critical' ? 'badge-critical'
       : s === 'high'     ? 'badge-high'
       : s === 'medium'   ? 'badge-medium'
       : 'badge-low';
}

export default function ExposuresPage() {
  const [statusFilter, setStatusFilter] = useState<Set<ExposureStatus>>(new Set());
  const [severity, setSeverity] = useState<Set<ExposureBrief['threat_severity']>>(new Set());
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState<{ tenant_id: string; threats_total: number;
    exposed: number; not_exposed: number; unknown: number; skipped_by_sector: number } | null>(null);
  const qc = useQueryClient();

  const { data, isLoading, isError, error } = useExposures({
    status:   statusFilter.size ? Array.from(statusFilter) : undefined,
    severity: severity.size ? Array.from(severity) : undefined,
  });

  const notLicensed = (error as { response?: { status?: number } })?.response?.status === 402;

  const onRecompute = async () => {
    setRunning(true);
    try {
      const r = await recomputeExposures();
      setLastRun(r);
      qc.invalidateQueries({ queryKey: ['exposures'] });
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-brand-700">Threat exposures</h1>
          <p className="mt-1 max-w-3xl text-sm text-slate-600">
            Each threat in the catalogue is evaluated against your current Registry,
            integrations, and observed AI usage. The verdict is one of <b>Exposed</b>,
            <b className="ml-1">Not exposed</b>, or <b className="ml-1">Unknown</b> — the
            last carries the exact telemetry source that would unblock the verdict.
            No predicate is left undefined.
          </p>
        </div>
        <button
          onClick={onRecompute}
          disabled={running}
          className="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {running ? 'Evaluating…' : 'Recompute exposures'}
        </button>
      </div>

      {lastRun && (
        <div className="rounded-md border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900">
          Evaluated {lastRun.threats_total} threats: {lastRun.exposed} exposed ·{' '}
          {lastRun.unknown} unknown · {lastRun.not_exposed} not exposed ·{' '}
          {lastRun.skipped_by_sector} skipped by sector overlay.
        </div>
      )}

      {notLicensed && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <div className="font-semibold">Module not licensed</div>
          <p className="mt-1">
            <code>AEGIS-THREAT</code> is required. Contact{' '}
            <a href="mailto:licensing@securisti.com" className="underline">
              licensing@securisti.com
            </a>.
          </p>
        </div>
      )}

      {!notLicensed && data && (
        <>
          <div className="grid gap-3 md:grid-cols-4">
            {(Object.keys(STATUS_LABEL) as ExposureStatus[]).map((s) => {
              const n = data.by_status[s] ?? 0;
              return (
                <div key={s} className="rounded-lg border bg-white p-4">
                  <div className="text-sm text-slate-500">{STATUS_LABEL[s].label}</div>
                  <div className="mt-1 text-3xl font-bold tabular-nums">{n}</div>
                </div>
              );
            })}
          </div>

          <div className="flex flex-wrap items-center gap-3 rounded-lg border bg-white p-3">
            <span className="text-xs text-slate-500 uppercase tracking-wide">Status</span>
            {(Object.keys(STATUS_LABEL) as ExposureStatus[]).map((s) => {
              const on = statusFilter.has(s);
              return (
                <button
                  key={s}
                  type="button"
                  onClick={() => {
                    const next = new Set(statusFilter);
                    if (on) next.delete(s); else next.add(s);
                    setStatusFilter(next);
                  }}
                  className={`rounded-md border px-2 py-1 text-xs font-medium ${
                    on ? STATUS_LABEL[s].cls + ' ring-1 ring-offset-1 ring-brand-500'
                       : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {STATUS_LABEL[s].label}
                </button>
              );
            })}

            <span className="ml-4 text-xs text-slate-500 uppercase tracking-wide">Severity</span>
            {(['critical', 'high', 'medium', 'low'] as const).map((s) => {
              const on = severity.has(s);
              return (
                <button
                  key={s}
                  type="button"
                  onClick={() => {
                    const next = new Set(severity);
                    if (on) next.delete(s); else next.add(s);
                    setSeverity(next);
                  }}
                  className={`rounded-md border px-2 py-1 text-xs font-medium ${
                    on ? sevBadge(s) + ' ring-1 ring-offset-1 ring-brand-500'
                       : 'border-slate-300 bg-white text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {s}
                </button>
              );
            })}

            <span className="ml-auto text-xs text-slate-500">
              {data.total} verdict{data.total === 1 ? '' : 's'}
            </span>
          </div>

          {isLoading && <div className="text-sm text-slate-500">Loading…</div>}

          {data.items.length === 0 && !isLoading && (
            <div className="rounded-lg border border-dashed bg-white p-12 text-center text-slate-500">
              <div className="font-medium">No exposure verdicts yet</div>
              <p className="mt-1 text-sm">
                Click <b>Recompute exposures</b> above to evaluate the catalogue
                against your current state.
              </p>
            </div>
          )}

          {data.items.length > 0 && (
            <div className="overflow-hidden rounded-lg border bg-white">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-2 w-32">Status</th>
                    <th className="px-4 py-2 w-44">Threat ID</th>
                    <th className="px-4 py-2">Title</th>
                    <th className="px-4 py-2 w-20">Severity</th>
                    <th className="px-4 py-2 w-44">Last evaluated</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.items.map((e) => (
                    <tr key={e.id} className="hover:bg-slate-50">
                      <td className="px-4 py-2 align-top">
                        <span className={STATUS_LABEL[e.status]?.cls ?? 'badge'}>
                          {STATUS_LABEL[e.status]?.label ?? e.status}
                        </span>
                      </td>
                      <td className="px-4 py-2 align-top">
                        <Link to={`/exposures/${e.threat_external_id}`}
                              className="font-mono text-xs text-brand-700 hover:underline">
                          {e.threat_external_id}
                        </Link>
                      </td>
                      <td className="px-4 py-2 align-top">
                        <Link to={`/exposures/${e.threat_external_id}`}
                              className="font-medium text-slate-800 hover:underline">
                          {e.threat_title}
                        </Link>
                      </td>
                      <td className="px-4 py-2 align-top">
                        <span className={sevBadge(e.threat_severity)}>{e.threat_severity}</span>
                      </td>
                      <td className="px-4 py-2 align-top text-xs text-slate-500">
                        {new Date(e.last_evaluated_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {isError && !notLicensed && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          Failed to load exposures: {(error as Error).message}
        </div>
      )}
    </div>
  );
}
