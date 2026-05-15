import { useMemo, useState } from 'react';
import {
  useAutoAssess,
  useFrameworkControls,
  useFrameworkMappings,
  useFrameworkScore,
  useFrameworks,
} from '@/hooks/useCompliance';
import type { ControlBrief, MappingDetail } from '@/hooks/useCompliance';

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

          <RequirementsCatalogue slug={slug} />

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

// ---------------------------------------------------------------------------
// Requirements catalogue — verbatim AI requirements for the selected framework
// ---------------------------------------------------------------------------
//
// What you see in this panel is what the auditor sees: the exact regulatory
// clause `requirement_text` (verbatim from the source document), the
// authoritative citation `source_ref`, and the deterministic control_id.
// The order on screen is the API order (sorted by control_id), so the visual
// output is stable across consequential runs.
function RequirementsCatalogue({ slug }: { slug: string }) {
  const { data: controls, isLoading } = useFrameworkControls(slug);
  const { data: mappings } = useFrameworkMappings(slug);
  const [q, setQ] = useState('');
  const [category, setCategory] = useState<string>('');
  const [openId, setOpenId] = useState<string | null>(null);

  // Group mappings by control_id so the panel can render each control's
  // pass/fail verdict per system with the explanation + evidence pinned
  // from the engine's last consequential run.
  const mappingsByControl = useMemo(() => {
    const map = new Map<string, MappingDetail[]>();
    (mappings ?? []).forEach((m) => {
      const arr = map.get(m.control_id) ?? [];
      arr.push(m);
      map.set(m.control_id, arr);
    });
    return map;
  }, [mappings]);

  // Worst-status-per-control rollup for the header badge. Order:
  //   not_implemented > partial > implemented > not_applicable.
  const rollupStatus = (controlId: string): MappingDetail['status'] | null => {
    const list = mappingsByControl.get(controlId);
    if (!list || list.length === 0) return null;
    const order: Record<MappingDetail['status'], number> = {
      not_implemented: 0,
      not_assessed: 1,
      partial: 2,
      implemented: 3,
      not_applicable: 4,
    };
    return list.reduce<MappingDetail['status']>(
      (worst, m) => (order[m.status] < order[worst] ? m.status : worst),
      'not_applicable',
    );
  };

  const categories = useMemo(() => {
    const set = new Set<string>();
    (controls ?? []).forEach((c) => c.category && set.add(c.category));
    return Array.from(set).sort();
  }, [controls]);

  const filtered: ControlBrief[] = useMemo(() => {
    if (!controls) return [];
    const needle = q.trim().toLowerCase();
    return controls.filter((c) => {
      if (category && c.category !== category) return false;
      if (!needle) return true;
      const haystack = `${c.control_id}\n${c.title}\n${c.requirement_text ?? ''}\n${c.source_ref ?? ''}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [controls, q, category]);

  return (
    <section className="rounded-lg border bg-white">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2">
        <div>
          <h2 className="font-semibold text-brand-700">Requirements catalogue</h2>
          <p className="text-xs text-slate-500">
            Verbatim regulatory text applicable to AI for this framework. Sorted
            by control ID; output is identical on every consequential run.
          </p>
        </div>
        <span className="text-xs text-slate-500">
          {controls ? `${filtered.length} of ${controls.length} requirements` : ''}
        </span>
      </header>

      <div className="flex flex-wrap items-center gap-2 border-b bg-slate-50 px-4 py-2">
        <input
          type="search"
          placeholder="Search ID, title or text…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="flex-1 min-w-[220px] rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
        >
          <option value="">All categories</option>
          {categories.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>

      {isLoading && <div className="p-4 text-sm text-slate-500">Loading requirements…</div>}

      {controls && filtered.length === 0 && !isLoading && (
        <div className="p-6 text-center text-sm text-slate-500">No requirements match the filter.</div>
      )}

      <ul className="divide-y divide-slate-100">
        {filtered.map((c) => {
          const isOpen = openId === c.id;
          return (
            <li key={c.id} className="px-4 py-3">
              <div
                role="button"
                tabIndex={0}
                onClick={() => setOpenId(isOpen ? null : c.id)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setOpenId(isOpen ? null : c.id); }}
                className="flex cursor-pointer items-start gap-3"
              >
                <code className="mt-0.5 shrink-0 rounded bg-slate-100 px-2 py-0.5 font-mono text-xs text-brand-700">
                  {c.control_id}
                </code>
                <div className="flex-1">
                  <div className="font-medium text-slate-800">{c.title}</div>
                  {c.source_ref && (
                    <div className="text-xs italic text-slate-500">{c.source_ref}</div>
                  )}
                </div>
                {c.category && (
                  <span className="badge bg-slate-100 text-slate-700">{c.category}</span>
                )}
                {!c.is_mandatory && (
                  <span className="badge bg-amber-100 text-amber-800">Optional</span>
                )}
                {(() => {
                  const s = rollupStatus(c.control_id);
                  if (!s) return null;
                  return <span className={STATUS_LABEL[s].cls}>{STATUS_LABEL[s].label}</span>;
                })()}
              </div>

              {isOpen && (
                <div className="ml-[5.5rem] mt-2 space-y-2 text-sm">
                  {c.requirement_text && (
                    <blockquote className="rounded-md border-l-4 border-brand-500 bg-slate-50 p-3 font-serif text-slate-800 whitespace-pre-wrap">
                      {c.requirement_text}
                    </blockquote>
                  )}
                  {c.description && (
                    <div>
                      <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
                        AEGIS interpretation
                      </span>
                      <p className="text-slate-700">{c.description}</p>
                    </div>
                  )}
                  {c.applies_to.length > 0 && (
                    <div className="text-xs text-slate-600">
                      <span className="font-medium uppercase tracking-wide text-slate-500">
                        Applies to:
                      </span>{' '}
                      {c.applies_to.join(', ')}
                    </div>
                  )}
                  {c.evidence_hints.length > 0 && (
                    <div className="text-xs text-slate-600">
                      <span className="font-medium uppercase tracking-wide text-slate-500">
                        Expected evidence:
                      </span>
                      <ul className="ml-4 list-disc">
                        {c.evidence_hints.map((h) => <li key={h}>{h}</li>)}
                      </ul>
                    </div>
                  )}

                  <MappingsForControl mappings={mappingsByControl.get(c.control_id) ?? []} />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Per-control assessment results (verdict + reasons + evidence refs)
// ---------------------------------------------------------------------------
//
// One row per AI system the engine evaluated this control against. Each row
// shows the verdict badge, the pipe-separated PREDICATE: VERDICT lines the
// engine produced, and the machine-readable evidence_refs that backed each
// line. When the tenant has no AI systems registered, the engine writes one
// tenant-scoped (ai_system_id=null) mapping with reason "No AI systems
// registered..." — that is what shows here, never an empty placeholder.
function MappingsForControl({ mappings }: { mappings: MappingDetail[] }) {
  if (mappings.length === 0) {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800">
        Not yet auto-assessed. Click <b>Run auto-assessment</b> above to evaluate this control.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
        Assessment results
      </div>
      {mappings.map((m) => {
        const reasons = (m.implementation_notes ?? '')
          .split(' | ')
          .map((s) => s.trim())
          .filter(Boolean);
        return (
          <div key={m.id} className="rounded-md border bg-slate-50 p-3">
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className={STATUS_LABEL[m.status]?.cls ?? 'badge'}>
                {STATUS_LABEL[m.status]?.label ?? m.status}
              </span>
              <span className="text-[11px] text-slate-500">
                {m.ai_system_id
                  ? <>system <code className="text-[10px]">{m.ai_system_id.slice(0, 8)}…</code></>
                  : <>tenant-scoped</>
                }
                {m.last_assessed_at && <> · {new Date(m.last_assessed_at).toLocaleString()}</>}
              </span>
            </div>
            {reasons.length > 0 && (
              <ul className="space-y-0.5 text-xs">
                {reasons.map((line, idx) => {
                  const verdict = line.includes(': PASSED')
                    ? 'text-emerald-700'
                    : line.includes(': FAILED')
                    ? 'text-red-700'
                    : 'text-slate-600';
                  return (
                    <li key={idx} className={`font-mono leading-snug ${verdict}`}>
                      {line}
                    </li>
                  );
                })}
              </ul>
            )}
            {m.evidence_refs.length > 0 && (
              <div className="mt-2 text-[11px] text-slate-500">
                <span className="font-medium uppercase tracking-wide">Evidence refs:</span>{' '}
                {m.evidence_refs.map((r) => (
                  <code key={r} className="ml-1 inline-block rounded bg-white px-1 py-0.5 text-slate-700">
                    {r}
                  </code>
                ))}
              </div>
            )}
          </div>
        );
      })}
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
