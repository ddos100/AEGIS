import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  decideMitigation,
  pushMitigation,
  rollbackMitigation,
  useMitigations,
  verifyMitigation,
  type MitigationBrief,
  type MitigationStatus,
} from '@/hooks/useThreats';

// Column order in the Kanban + the badge style for each status.
const COLUMNS: { status: MitigationStatus; label: string; cls: string }[] = [
  { status: 'proposed',    label: 'Proposed',    cls: 'bg-amber-50 border-amber-200' },
  { status: 'queued',      label: 'Queued',      cls: 'bg-blue-50 border-blue-200' },
  { status: 'applied',     label: 'Applied',     cls: 'bg-emerald-50 border-emerald-200' },
  { status: 'verified',    label: 'Verified',    cls: 'bg-emerald-100 border-emerald-300' },
  { status: 'drifted',     label: 'Drifted',     cls: 'bg-red-50 border-red-200' },
  { status: 'rejected',    label: 'Rejected',    cls: 'bg-slate-50 border-slate-200' },
];

const STATUS_BADGE: Record<MitigationStatus, string> = {
  proposed:   'badge bg-amber-100 text-amber-800',
  queued:     'badge bg-blue-100 text-blue-800',
  applied:    'badge bg-emerald-100 text-emerald-800',
  verified:   'badge bg-emerald-200 text-emerald-900',
  drifted:    'badge-critical',
  rejected:   'badge bg-slate-200 text-slate-700',
  dismissed:  'badge bg-slate-100 text-slate-600',
  rolled_back:'badge bg-slate-200 text-slate-700',
  failed:     'badge-critical',
};

function sevBadge(s: MitigationBrief['threat_severity']) {
  return s === 'critical' ? 'badge-critical'
       : s === 'high'     ? 'badge-high'
       : s === 'medium'   ? 'badge-medium'
       : 'badge-low';
}

export default function MitigationsPage() {
  const { data, isLoading, isError, error } = useMitigations();
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);

  const notLicensed = (error as { response?: { status?: number } })?.response?.status === 402;

  const onDecide = async (id: string, decision: 'approve' | 'reject' | 'dismiss') => {
    setBusy(id);
    try {
      const reason = decision !== 'approve'
        ? (window.prompt(`Reason for ${decision}? (optional)`) || undefined)
        : undefined;
      await decideMitigation(id, decision, reason);
      qc.invalidateQueries({ queryKey: ['mitigations'] });
    } finally {
      setBusy(null);
    }
  };

  const onPush = async (id: string) => {
    setBusy(id);
    try {
      const r = await pushMitigation(id);
      if (r.error) window.alert(`Push failed: ${r.error}`);
      qc.invalidateQueries({ queryKey: ['mitigations'] });
    } finally {
      setBusy(null);
    }
  };

  const onVerify = async (id: string) => {
    setBusy(id);
    try {
      const r = await verifyMitigation(id);
      if (r.error) window.alert(`Verify error: ${r.error}`);
      qc.invalidateQueries({ queryKey: ['mitigations'] });
    } finally {
      setBusy(null);
    }
  };

  const onRollback = async (id: string) => {
    if (!window.confirm('Roll back this mitigation? This is irreversible at the vendor.')) return;
    setBusy(id);
    try {
      const reason = window.prompt('Reason for rollback? (optional)') || undefined;
      await rollbackMitigation(id, reason);
      qc.invalidateQueries({ queryKey: ['mitigations'] });
    } finally {
      setBusy(null);
    }
  };

  const byCol: Record<MitigationStatus, MitigationBrief[]> = {
    proposed: [], queued: [], applied: [], verified: [], drifted: [],
    rejected: [], dismissed: [], rolled_back: [], failed: [],
  };
  (data?.items ?? []).forEach((m) => byCol[m.status]?.push(m));

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-700">Mitigations</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          Proposed mitigations are generated automatically when an exposure verdict is
          <code className="mx-1 rounded bg-slate-100 px-1">exposed</code>. AEGIS does not push
          anything to your integrations in v1 — every action is propose-only and awaits an
          operator decision. Approve to move the action into the queue for the verification
          loop (Phase 7.5).
        </p>
      </div>

      {notLicensed && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <code>AEGIS-THREAT</code> not licensed. Contact licensing@securisti.com.
        </div>
      )}

      {!notLicensed && data && (
        <>
          <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
            {COLUMNS.map((col) => (
              <div key={col.status} className="rounded-lg border bg-white p-4">
                <div className="text-xs text-slate-500">{col.label}</div>
                <div className="mt-1 text-3xl font-bold tabular-nums">
                  {data.by_status[col.status] ?? 0}
                </div>
              </div>
            ))}
          </div>

          {isLoading && <div className="text-sm text-slate-500">Loading…</div>}

          {data.items.length === 0 && (
            <div className="rounded-lg border border-dashed bg-white p-12 text-center text-slate-500">
              <div className="font-medium">No mitigations proposed yet</div>
              <p className="mt-1 text-sm">
                Run <Link to="/exposures" className="text-brand-700 underline">Recompute exposures</Link>{' '}
                — every threat with an <b>exposed</b> verdict generates a proposed mitigation
                from the threat's <code>mitigation.preferred[]</code> block.
              </p>
            </div>
          )}

          {data.items.length > 0 && (
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {COLUMNS.filter(c => byCol[c.status].length > 0).map((col) => (
                <section key={col.status} className={`rounded-lg border ${col.cls} p-2`}>
                  <header className="px-2 py-1 text-xs font-medium uppercase tracking-wide text-slate-700">
                    {col.label} ({byCol[col.status].length})
                  </header>
                  <div className="space-y-2">
                    {byCol[col.status].map((m) => (
                      <article key={m.id} className="rounded-md border bg-white p-3 text-sm shadow-sm">
                        <div className="flex items-center justify-between gap-2">
                          <Link to={`/threats/${m.threat_external_id}`}
                                className="font-mono text-xs text-brand-700 hover:underline">
                            {m.threat_external_id}
                          </Link>
                          <span className={sevBadge(m.threat_severity)}>{m.threat_severity}</span>
                        </div>
                        <div className="mt-1 font-medium text-slate-800">{m.threat_title}</div>
                        <div className="mt-1 flex items-center gap-1 text-xs">
                          <code className="rounded bg-slate-100 px-1.5 py-0.5 text-brand-700">{m.integration}</code>
                          <span className="text-slate-500">→</span>
                          <code className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-700">{m.action}</code>
                        </div>
                        {m.preference === 'alternate' && (
                          <div className="mt-1 text-[11px] text-slate-500">alternate (preferred path failed or skipped)</div>
                        )}
                        {m.requires_module && (
                          <div className="mt-1 text-[11px]">
                            <span className="rounded bg-amber-100 px-1 py-0.5 text-amber-800">
                              requires {m.requires_module}
                            </span>
                          </div>
                        )}
                        {m.status_reason && (
                          <div className="mt-1 text-[11px] italic text-slate-600">"{m.status_reason}"</div>
                        )}
                        {m.status === 'proposed' && (
                          <div className="mt-2 flex gap-1">
                            <button
                              disabled={busy === m.id}
                              onClick={() => onDecide(m.id, 'approve')}
                              className="rounded border border-emerald-300 bg-white px-2 py-1 text-xs text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
                            >
                              Approve
                            </button>
                            <button
                              disabled={busy === m.id}
                              onClick={() => onDecide(m.id, 'reject')}
                              className="rounded border border-red-300 bg-white px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-50"
                            >
                              Reject
                            </button>
                            <button
                              disabled={busy === m.id}
                              onClick={() => onDecide(m.id, 'dismiss')}
                              className="rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                            >
                              Dismiss
                            </button>
                          </div>
                        )}
                        {m.status === 'queued' && (
                          <div className="mt-2 flex gap-1">
                            <button
                              disabled={busy === m.id}
                              onClick={() => onPush(m.id)}
                              className="rounded border border-blue-300 bg-white px-2 py-1 text-xs text-blue-700 hover:bg-blue-50 disabled:opacity-50"
                              title="Run adapter.apply() — DRY-RUN at the vendor in v1"
                            >
                              Push (dry-run)
                            </button>
                            <button
                              disabled={busy === m.id}
                              onClick={() => onDecide(m.id, 'reject')}
                              className="rounded border border-red-300 bg-white px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-50"
                            >
                              Cancel
                            </button>
                          </div>
                        )}
                        {(m.status === 'applied' || m.status === 'verified' || m.status === 'drifted') && (
                          <div className="mt-2 flex gap-1">
                            <button
                              disabled={busy === m.id}
                              onClick={() => onVerify(m.id)}
                              className="rounded border border-brand-500 bg-white px-2 py-1 text-xs text-brand-700 hover:bg-brand-50 disabled:opacity-50"
                            >
                              Verify now
                            </button>
                            <button
                              disabled={busy === m.id}
                              onClick={() => onRollback(m.id)}
                              className="rounded border border-red-300 bg-white px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-50"
                            >
                              Rollback
                            </button>
                          </div>
                        )}
                        {m.status === 'failed' && (
                          <div className="mt-2 flex gap-1">
                            <button
                              disabled={busy === m.id}
                              onClick={() => onPush(m.id)}
                              className="rounded border border-blue-300 bg-white px-2 py-1 text-xs text-blue-700 hover:bg-blue-50 disabled:opacity-50"
                            >
                              Retry push
                            </button>
                            <button
                              disabled={busy === m.id}
                              onClick={() => onRollback(m.id)}
                              className="rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                            >
                              Abandon
                            </button>
                          </div>
                        )}
                        {m.status !== 'proposed' && (
                          <div className="mt-2 flex items-center justify-between text-[11px] text-slate-500">
                            <span className={STATUS_BADGE[m.status]}>{m.status}</span>
                            <span>
                              {m.approved_at && `approved ${new Date(m.approved_at).toLocaleString()}`}
                            </span>
                          </div>
                        )}
                      </article>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </>
      )}

      {isError && !notLicensed && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          Failed to load mitigations: {(error as Error).message}
        </div>
      )}
    </div>
  );
}
