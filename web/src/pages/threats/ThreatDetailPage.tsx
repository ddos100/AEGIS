import { Link, useParams } from 'react-router-dom';
import { useThreat } from '@/hooks/useThreats';

function sevClass(s: string) {
  return s === 'critical' ? 'badge-critical'
       : s === 'high'     ? 'badge-high'
       : s === 'medium'   ? 'badge-medium'
       : 'badge-low';
}

interface MitigationStep {
  integration: string;
  action: string;
  params?: Record<string, unknown>;
  requires_module?: string;
}

export default function ThreatDetailPage() {
  const { threatId = '' } = useParams();
  const { data, isLoading, isError, error } = useThreat(threatId);

  const notLicensed = (error as { response?: { status?: number } })?.response?.status === 402;

  if (notLicensed) {
    return (
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
        <code>AEGIS-THREAT</code> module not licensed. Contact licensing@securisti.com.
      </div>
    );
  }
  if (isLoading) return <div className="text-sm text-slate-500">Loading…</div>;
  if (isError || !data) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
        Failed to load threat.
      </div>
    );
  }

  const preferred  = (data.mitigation?.preferred ?? []) as MitigationStep[];
  const alternates = (data.mitigation?.alternates ?? []) as MitigationStep[];

  return (
    <div className="space-y-5">
      <div>
        <Link to="/threats" className="text-sm text-brand-600 hover:underline">← All threats</Link>
        <div className="mt-2 flex items-center gap-3">
          <code className="rounded bg-slate-100 px-2 py-1 font-mono text-sm text-brand-700">
            {data.threat_id}
          </code>
          <span className={sevClass(data.severity)}>{data.severity}</span>
        </div>
        <h1 className="mt-2 text-2xl font-bold text-slate-800">{data.title}</h1>
        <div className="mt-1 text-sm italic text-slate-500">{data.source_ref}</div>
      </div>

      <section className="rounded-lg border bg-white p-4">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">Verbatim description</h2>
        <blockquote className="mt-2 rounded-md border-l-4 border-brand-500 bg-slate-50 p-3 font-serif text-slate-800 whitespace-pre-wrap">
          {data.verbatim_description}
        </blockquote>
        {data.description && (
          <div className="mt-3">
            <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
              AEGIS interpretation
            </span>
            <p className="text-slate-700">{data.description}</p>
          </div>
        )}
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-lg border bg-white p-4">
          <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">Classification</h2>
          <dl className="mt-2 space-y-2 text-sm">
            <div>
              <dt className="font-medium text-slate-600">Classes</dt>
              <dd className="mt-0.5 flex flex-wrap gap-1">
                {data.classes.map((c) => (
                  <span key={c} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs">{c}</span>
                ))}
              </dd>
            </div>
            <div>
              <dt className="font-medium text-slate-600">Vectors</dt>
              <dd className="mt-0.5 flex flex-wrap gap-1">
                {data.vectors.map((v) => (
                  <span key={v} className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700">{v}</span>
                ))}
              </dd>
            </div>
            {data.mitre_atlas_ids.length > 0 && (
              <div>
                <dt className="font-medium text-slate-600">MITRE ATLAS</dt>
                <dd>{data.mitre_atlas_ids.join(', ')}</dd>
              </div>
            )}
            {data.owasp_llm_ids.length > 0 && (
              <div>
                <dt className="font-medium text-slate-600">OWASP LLM Top 10</dt>
                <dd>{data.owasp_llm_ids.join(', ')}</dd>
              </div>
            )}
            {data.sector_amplifiers.length > 0 && (
              <div>
                <dt className="font-medium text-slate-600">Sector amplifiers</dt>
                <dd>{data.sector_amplifiers.join(', ')}</dd>
              </div>
            )}
            {data.compliance_implications.length > 0 && (
              <div>
                <dt className="font-medium text-slate-600">Compliance implications</dt>
                <dd className="mt-0.5 flex flex-wrap gap-1">
                  {data.compliance_implications.map((c) => (
                    <code key={c} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-brand-700">{c}</code>
                  ))}
                </dd>
              </div>
            )}
          </dl>
        </section>

        <section className="rounded-lg border bg-white p-4">
          <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">Exposure check (predicate)</h2>
          <pre className="mt-2 overflow-auto rounded-md bg-slate-50 p-3 text-xs text-slate-800">
            {JSON.stringify(data.exposure_check, null, 2)}
          </pre>
          <p className="mt-2 text-xs text-slate-500">
            Phase 7.3 evaluates this predicate against the tenant's observed state and writes
            a per-tenant exposure verdict (<code>exposed</code> / <code>not_exposed</code> /
            <code>unknown</code>) with evidence refs.
          </p>
        </section>
      </div>

      <section className="rounded-lg border bg-white p-4">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">Recommended mitigations</h2>
        <p className="mt-1 text-xs text-slate-500">
          Phase 7.4 turns these into proposed actions on configured integrations.
          Until then this list documents the runbook AEGIS will follow.
        </p>

        {preferred.length > 0 && (
          <>
            <div className="mt-3 text-xs font-medium uppercase tracking-wide text-emerald-700">Preferred</div>
            <ul className="mt-1 space-y-1.5">
              {preferred.map((m, i) => (
                <li key={i} className="rounded-md border bg-slate-50 p-2 text-xs">
                  <code className="text-brand-700">{m.integration}</code>
                  <code className="ml-2 text-slate-700">{m.action}</code>
                  {m.requires_module && (
                    <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-amber-800">
                      requires {m.requires_module}
                    </span>
                  )}
                  {m.params && (
                    <pre className="mt-1 overflow-auto text-[11px] text-slate-600">
                      {JSON.stringify(m.params, null, 2)}
                    </pre>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}

        {alternates.length > 0 && (
          <>
            <div className="mt-4 text-xs font-medium uppercase tracking-wide text-slate-600">Alternates</div>
            <ul className="mt-1 space-y-1.5">
              {alternates.map((m, i) => (
                <li key={i} className="rounded-md border bg-slate-50 p-2 text-xs">
                  <code className="text-brand-700">{m.integration}</code>
                  <code className="ml-2 text-slate-700">{m.action}</code>
                </li>
              ))}
            </ul>
          </>
        )}

        {preferred.length === 0 && alternates.length === 0 && (
          <p className="mt-2 text-xs text-slate-500">No mitigation recommendations declared for this threat.</p>
        )}
      </section>

      <section className="rounded-lg border bg-white p-4">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">Evidence hints</h2>
        {data.evidence_hints.length > 0 ? (
          <ul className="mt-2 list-disc pl-5 text-sm text-slate-700">
            {data.evidence_hints.map((h, i) => <li key={i}>{h}</li>)}
          </ul>
        ) : (
          <p className="mt-2 text-xs text-slate-500">No evidence hints declared.</p>
        )}
      </section>

      <div className="text-[11px] text-slate-400">
        Catalogue version {data.catalogue_version} · last updated {data.last_updated}
      </div>
    </div>
  );
}
