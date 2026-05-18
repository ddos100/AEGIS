import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useThreats, type ThreatBrief } from '@/hooks/useThreats';

// Static metadata mirrors catalogue/threats/schema.yaml enums. Kept here so
// the filter pickers render without an extra backend round-trip; if the
// schema gains a new enum value the backend's `/_/stats` endpoint will
// still return data — the filter just won't surface that option until this
// list is updated. Engineering review on every catalogue schema change
// catches that.
const SEVERITIES: ThreatBrief['severity'][] = ['critical', 'high', 'medium', 'low'];

const VECTOR_LABEL: Record<string, string> = {
  browser_webapp:           'Browser web app',
  browser_extension:        'Browser extension',
  desktop_client:           'Desktop client',
  coding_assistant:         'Coding assistant',
  cli_sdk:                  'CLI / SDK',
  mcp_agent:                'MCP / Agent',
  embedded_saas:            'Embedded SaaS',
  cloud_ai_control_plane:   'Cloud AI control plane',
  local_model:              'Local model',
};

const CLASS_LABEL: Record<string, string> = {
  data_exfiltration:         'Data exfiltration',
  cross_border_transfer:     'Cross-border transfer',
  direct_prompt_injection:   'Direct prompt injection',
  indirect_prompt_injection: 'Indirect prompt injection',
  output_oversharing:        'Output oversharing',
  supply_chain:              'Supply chain',
  insecure_install:          'Insecure install',
  excess_agent_permissions:  'Excess agent permissions',
  autonomous_agent_loop_out: 'Autonomous agent loop-out',
  model_integrity:           'Model integrity',
  jailbreak:                 'Jailbreak',
  deepfake:                  'Deepfake',
  regulated_secret_leak:     'Regulated secret leak',
  cost_availability_abuse:   'Cost / availability abuse',
};

function sevBadge(s: ThreatBrief['severity']) {
  return s === 'critical' ? 'badge-critical'
       : s === 'high'     ? 'badge-high'
       : s === 'medium'   ? 'badge-medium'
       : 'badge-low';
}

export default function ThreatsBrowsePage() {
  const [q, setQ] = useState('');
  const [severities, setSeverities] = useState<Set<ThreatBrief['severity']>>(new Set());
  const [vector, setVector] = useState<string>('');
  const [klass, setKlass]   = useState<string>('');
  const [page, setPage]     = useState(1);

  const query = useMemo(() => ({
    q: q || undefined,
    severity: severities.size > 0 ? Array.from(severities) : undefined,
    vector:   vector || undefined,
    class:    klass  || undefined,
    page,
    per_page: 30,
  }), [q, severities, vector, klass, page]);

  const { data, isLoading, isError, error } = useThreats(query);

  // 402 from the API means the tenant doesn't have AEGIS-THREAT.
  const notLicensed = (error as { response?: { status?: number } })?.response?.status === 402;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-700">Threat catalogue</h1>
        <p className="mt-1 text-sm text-slate-600 max-w-3xl">
          AI-specific threats curated from MITRE ATLAS, OWASP LLM Top 10, NIST AI RMF,
          DPDPA / RBI / IRDAI / SEBI, and SCLLP research. Every entry carries a verbatim
          citation (<code>source_ref</code>), a non-empty <code>exposure_check</code>
          predicate, and recommended mitigations referencing your configured integrations.
        </p>
      </div>

      {notLicensed && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <div className="font-semibold">Module not licensed</div>
          <p className="mt-1">
            <code>AEGIS-THREAT</code> is required to browse the threat catalogue.
            Contact <a href="mailto:licensing@securisti.com" className="underline">
            licensing@securisti.com</a> to procure this module.
          </p>
        </div>
      )}

      {!notLicensed && (
        <>
          <div className="flex flex-wrap items-center gap-3 rounded-lg border bg-white p-3">
            <input
              type="search"
              placeholder="Search ID, title, or citation…"
              value={q}
              onChange={(e) => { setQ(e.target.value); setPage(1); }}
              className="flex-1 min-w-[260px] rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
            <select
              value={vector}
              onChange={(e) => { setVector(e.target.value); setPage(1); }}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            >
              <option value="">All vectors</option>
              {Object.entries(VECTOR_LABEL).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
            <select
              value={klass}
              onChange={(e) => { setKlass(e.target.value); setPage(1); }}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            >
              <option value="">All classes</option>
              {Object.entries(CLASS_LABEL).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
            <div className="flex items-center gap-1">
              {SEVERITIES.map((s) => {
                const on = severities.has(s);
                return (
                  <button
                    key={s}
                    type="button"
                    onClick={() => {
                      const next = new Set(severities);
                      if (on) next.delete(s); else next.add(s);
                      setSeverities(next);
                      setPage(1);
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
            </div>
            {data && (
              <span className="ml-auto text-xs text-slate-500">
                {data.total} threat{data.total === 1 ? '' : 's'}
              </span>
            )}
          </div>

          {isLoading && <div className="text-sm text-slate-500">Loading…</div>}
          {isError && !notLicensed && (
            <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              Failed to load threats: {(error as Error).message}
            </div>
          )}

          {data && (
            <div className="overflow-hidden rounded-lg border bg-white">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-2 w-40">Threat ID</th>
                    <th className="px-4 py-2">Title</th>
                    <th className="px-4 py-2 w-20">Severity</th>
                    <th className="px-4 py-2">Classes</th>
                    <th className="px-4 py-2">Vectors</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.items.map((t) => (
                    <tr key={t.id} className="hover:bg-slate-50">
                      <td className="px-4 py-2 align-top">
                        <Link to={`/threats/${t.threat_id}`}
                              className="font-mono text-xs text-brand-700 hover:underline">
                          {t.threat_id}
                        </Link>
                      </td>
                      <td className="px-4 py-2 align-top">
                        <Link to={`/threats/${t.threat_id}`}
                              className="font-medium text-slate-800 hover:underline">
                          {t.title}
                        </Link>
                        <div className="mt-0.5 text-xs italic text-slate-500">{t.source_ref}</div>
                      </td>
                      <td className="px-4 py-2 align-top">
                        <span className={sevBadge(t.severity)}>{t.severity}</span>
                      </td>
                      <td className="px-4 py-2 align-top">
                        <div className="flex flex-wrap gap-1">
                          {t.classes.map((c) => (
                            <span key={c} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700">
                              {CLASS_LABEL[c] ?? c}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-4 py-2 align-top">
                        <div className="flex flex-wrap gap-1">
                          {t.vectors.map((v) => (
                            <span key={v} className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700">
                              {VECTOR_LABEL[v] ?? v}
                            </span>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {data && data.pages > 1 && (
            <div className="flex items-center justify-center gap-2 text-sm">
              <button disabled={data.page <= 1} onClick={() => setPage(p => Math.max(1, p - 1))}
                      className="rounded border border-slate-300 bg-white px-3 py-1 disabled:opacity-50">
                Prev
              </button>
              <span className="text-slate-600">Page {data.page} of {data.pages}</span>
              <button disabled={data.page >= data.pages} onClick={() => setPage(p => p + 1)}
                      className="rounded border border-slate-300 bg-white px-3 py-1 disabled:opacity-50">
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
