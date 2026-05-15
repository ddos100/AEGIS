import { useState } from 'react';
import {
  useAutoAssess,
  useFrameworkScore,
  useFrameworks,
} from '@/hooks/useCompliance';

const STATUS_LABEL: Record<string, { label: string; cls: string }> = {
  implemented:     { label: 'Implemented',     cls: 'badge-low' },
  partial:         { label: 'Partial',         cls: 'badge-medium' },
  not_implemented: { label: 'Not implemented', cls: 'badge-critical' },
  not_applicable:  { label: 'N/A',             cls: 'badge bg-slate-100 text-slate-700' },
  not_assessed:    { label: 'Not assessed',    cls: 'badge bg-slate-100 text-slate-700' },
};

export default function CompliancePage() {
  const { data: frameworks } = useFrameworks();
  const [selected, setSelected] = useState<string | null>(null);
  const slug = selected || frameworks?.[0]?.slug;
  const { data: score, isLoading } = useFrameworkScore(slug);
  const assess = useAutoAssess();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-700">Compliance</h1>
        <p className="text-sm text-slate-600">
          Auto-assessment maps Registry state to controls in each regulatory framework.
          The engine never marks a control "implemented" — that requires human attestation.
          Run the audit, then attest the gaps in the mappings view.
        </p>
      </div>

      {frameworks && frameworks.length === 0 && (
        <div className="rounded-lg border border-dashed bg-white p-12 text-center text-slate-500">
          <div className="font-medium">No frameworks imported</div>
          <div className="mt-2 text-sm">
            From the repo root:&nbsp;
            <code className="rounded bg-slate-100 px-2 py-0.5">make framework-import</code>
          </div>
        </div>
      )}

      {frameworks && frameworks.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {frameworks.map((f) => (
            <button
              key={f.slug}
              onClick={() => setSelected(f.slug)}
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                f.slug === slug
                  ? 'bg-brand-600 text-white'
                  : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
            >
              {f.name}
              {f.jurisdiction && <span className="ml-1 opacity-60">({f.jurisdiction})</span>}
            </button>
          ))}
        </div>
      )}

      {slug && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-slate-600">
            Auto-assessment runs the predicates declared in each YAML against your Registry —
            results land as 'partial' or 'not_implemented' mappings.
          </div>
          <button
            onClick={() => assess.mutate(slug)}
            disabled={assess.isPending}
            className="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {assess.isPending ? 'Assessing…' : 'Run auto-assessment'}
          </button>
        </div>
      )}

      {isLoading && <div className="text-sm text-slate-500">Loading score…</div>}

      {score && (
        <>
          <section className="grid gap-4 md:grid-cols-4">
            <StatCard label="Compliance score" value={`${score.score_pct.toFixed(1)}%`}
                      hint={`${score.total_controls} controls`} />
            <StatCard label="Implemented"     value={score.by_status.implemented ?? 0} />
            <StatCard label="Partial"         value={score.by_status.partial ?? 0} />
            <StatCard label="Not implemented" value={score.by_status.not_implemented ?? 0} />
          </section>

          <section className="rounded-lg border bg-white">
            <header className="flex items-center justify-between border-b px-4 py-2">
              <h2 className="font-semibold text-brand-700">Status distribution</h2>
            </header>
            <div className="p-4 space-y-2">
              {Object.entries(STATUS_LABEL).map(([key, def]) => {
                const count = score.by_status[key] ?? 0;
                const pct = score.total_controls > 0
                  ? Math.round((count / score.total_controls) * 100) : 0;
                return (
                  <div key={key} className="flex items-center gap-3 text-sm">
                    <div className="w-32"><span className={def.cls}>{def.label}</span></div>
                    <div className="flex-1 h-2 overflow-hidden rounded-full bg-slate-100">
                      <div className="h-full bg-brand-500" style={{ width: `${pct}%` }} />
                    </div>
                    <div className="w-16 text-right tabular-nums text-slate-600">{count} ({pct}%)</div>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="rounded-lg border bg-white">
            <header className="flex items-center justify-between border-b px-4 py-2">
              <h2 className="font-semibold text-brand-700">Outstanding gaps</h2>
              <span className="text-xs text-slate-500">{score.gaps.length} controls</span>
            </header>
            {score.gaps.length === 0 ? (
              <div className="p-6 text-center text-sm text-slate-500">
                No gaps — every control is at least partially implemented or marked not-applicable.
              </div>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-2 w-40">Control</th>
                    <th className="px-4 py-2">Title</th>
                    <th className="px-4 py-2 w-40">Category</th>
                    <th className="px-4 py-2 w-40">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {score.gaps.map((g) => (
                    <tr key={g.control_id}>
                      <td className="px-4 py-2 font-mono text-xs text-slate-700">{g.control_id}</td>
                      <td className="px-4 py-2">{g.title}</td>
                      <td className="px-4 py-2 text-slate-600">{g.category || '—'}</td>
                      <td className="px-4 py-2">
                        <span className={STATUS_LABEL[g.status]?.cls ?? 'badge'}>
                          {STATUS_LABEL[g.status]?.label ?? g.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </div>
  );
}

function StatCard({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div className="rounded-lg border bg-white p-4">
      <div className="text-sm text-slate-500">{label}</div>
      <div className="mt-1 text-3xl font-bold tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-400">{hint}</div>}
    </div>
  );
}
