import { Link, useParams } from 'react-router-dom';
import { useExposure, type ExposureStatus } from '@/hooks/useThreats';

const STATUS_BADGE: Record<ExposureStatus, string> = {
  exposed:     'badge-critical',
  unknown:     'badge-medium',
  not_exposed: 'badge-low',
  mitigated:   'badge bg-emerald-100 text-emerald-800',
};

const TELEMETRY_LABEL: Record<string, string> = {
  network_telemetry:  'Network telemetry (Zscaler / NGFW / DNS)',
  browser_extension:  'AEGIS browser extension',
  idp:                'IdP connector (Entra ID / Okta)',
  cloud_inventory:    'Cloud AI inventory (AWS / Azure / GCP)',
  m365_audit:         'M365 audit log connector',
  endpoint_agent:     'AEGIS Endpoint Agent (Phase 7.6)',
  ai_system_registry: 'AI System Registry (catalogue-match needed)',
  engine_update:      'AEGIS engine update (unsupported predicate)',
};

export default function ExposureDetailPage() {
  const { threatId = '' } = useParams();
  const { data, isLoading, isError, error } = useExposure(threatId);
  const notLicensed = (error as { response?: { status?: number } })?.response?.status === 402;
  const notFound    = (error as { response?: { status?: number } })?.response?.status === 404;

  if (isLoading) return <div className="text-sm text-slate-500">Loading…</div>;
  if (notLicensed) {
    return (
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
        <code>AEGIS-THREAT</code> module not licensed. Contact licensing@securisti.com.
      </div>
    );
  }
  if (notFound) {
    return (
      <div className="space-y-3">
        <Link to="/exposures" className="text-sm text-brand-600 hover:underline">← All exposures</Link>
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          No exposure verdict yet for <code>{threatId}</code>. Go back and click{' '}
          <b>Recompute exposures</b> to evaluate the catalogue.
        </div>
      </div>
    );
  }
  if (isError || !data) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
        Failed to load exposure.
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <Link to="/exposures" className="text-sm text-brand-600 hover:underline">← All exposures</Link>
        <div className="mt-2 flex items-center gap-3">
          <span className={STATUS_BADGE[data.status]}>{data.status.replace('_', ' ')}</span>
          <code className="rounded bg-slate-100 px-2 py-1 font-mono text-sm text-brand-700">
            {data.threat_external_id}
          </code>
          <Link to={`/threats/${data.threat_external_id}`}
                className="text-xs text-brand-600 hover:underline">
            See threat record →
          </Link>
        </div>
        <h1 className="mt-2 text-2xl font-bold text-slate-800">{data.threat_title}</h1>
        <div className="mt-1 text-sm italic text-slate-500">{data.threat_source_ref}</div>
        <div className="mt-1 text-xs text-slate-500">
          Last evaluated {new Date(data.last_evaluated_at).toLocaleString()}
        </div>
      </div>

      {data.status === 'unknown' && data.missing_telemetry.length > 0 && (
        <section className="rounded-lg border border-amber-300 bg-amber-50 p-4">
          <h2 className="text-sm font-medium uppercase tracking-wide text-amber-900">
            Telemetry gap
          </h2>
          <p className="mt-1 text-sm text-amber-900">
            One or more predicates could not be evaluated because the underlying
            data source is not yet integrated.
          </p>
          <ul className="mt-2 space-y-1 text-sm">
            {data.missing_telemetry.map((t) => (
              <li key={t} className="flex items-center gap-2">
                <span className="rounded bg-amber-200 px-2 py-0.5 text-xs font-mono text-amber-900">
                  {t}
                </span>
                <span className="text-amber-900">{TELEMETRY_LABEL[t] ?? t}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="rounded-lg border bg-white p-4">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">
          Predicate verdicts
        </h2>
        <ul className="mt-2 space-y-1 text-sm">
          {data.reasons.map((r, i) => {
            const color = r.includes(': PASSED') ? 'text-emerald-700'
                        : r.includes(': FAILED') ? 'text-red-700'
                        : 'text-amber-700';
            return (
              <li key={i} className={`font-mono leading-snug ${color}`}>{r}</li>
            );
          })}
        </ul>
      </section>

      {data.evidence_refs.length > 0 && (
        <section className="rounded-lg border bg-white p-4">
          <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">
            Evidence references
          </h2>
          <div className="mt-2 flex flex-wrap gap-1">
            {data.evidence_refs.map((r) => (
              <code key={r} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700">
                {r}
              </code>
            ))}
          </div>
        </section>
      )}

      <section className="rounded-lg border bg-white p-4">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500">
          Verbatim threat description
        </h2>
        <blockquote className="mt-2 rounded-md border-l-4 border-brand-500 bg-slate-50 p-3 font-serif text-slate-800 whitespace-pre-wrap">
          {data.threat_verbatim_description}
        </blockquote>
      </section>
    </div>
  );
}
