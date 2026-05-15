import { useState } from 'react';
import {
  useDeletePolicy,
  useImportTemplate,
  usePolicies,
  usePolicyTemplates,
  useUpdatePolicy,
  useViolations,
} from '@/hooks/useRiskPolicy';
import type { PolicyDetail, ViolationRow } from '@/types/risk';

const ACTION_COLORS: Record<string, string> = {
  allow:             'badge-low',
  monitor:           'badge bg-slate-100 text-slate-700',
  alert:             'badge-medium',
  block:             'badge-critical',
  require_approval:  'badge-high',
};

export default function PoliciesPage() {
  const { data: policies, isLoading } = usePolicies();
  const { data: templates } = usePolicyTemplates();
  const importTpl = useImportTemplate();
  const [tab, setTab] = useState<'policies' | 'violations'>('policies');

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-700">Policy Engine</h1>
        <p className="text-sm text-slate-600">
          Rules are evaluated in ascending-priority order; first match wins.
          Conditions use AND semantics. Non-allow actions are recorded as violations.
        </p>
      </div>

      <div className="flex gap-2 border-b">
        {(['policies', 'violations'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
              tab === t ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-600'
            }`}
          >
            {t === 'policies' ? 'Policies' : 'Violations'}
          </button>
        ))}
      </div>

      {tab === 'policies' && (
        <>
          {templates && templates.length > 0 && (
            <section className="rounded-lg border bg-white">
              <header className="border-b px-4 py-2">
                <h2 className="font-semibold text-brand-700">Quick-start templates</h2>
              </header>
              <div className="grid gap-3 p-4 md:grid-cols-2">
                {templates.map((t) => (
                  <div key={t.id} className="flex items-start justify-between rounded border p-3">
                    <div className="flex-1">
                      <div className="font-medium">{t.name}</div>
                      <div className="mt-1 text-xs text-slate-500">{t.description}</div>
                      <div className="mt-1 text-xs text-slate-400">{t.rule_count} rules</div>
                    </div>
                    <button
                      onClick={() => importTpl.mutate(t.id)}
                      disabled={importTpl.isPending}
                      className="ml-3 shrink-0 rounded-md bg-brand-600 px-3 py-1 text-xs font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                    >
                      Import
                    </button>
                  </div>
                ))}
              </div>
            </section>
          )}

          {isLoading && <div className="text-sm text-slate-500">Loading…</div>}

          {policies && policies.length === 0 && (
            <div className="rounded-lg border border-dashed bg-white p-12 text-center text-slate-500">
              <div className="font-medium">No policies yet</div>
              <div className="mt-1 text-sm">Import a template above to get started.</div>
            </div>
          )}

          {policies && policies.length > 0 && (
            <div className="overflow-hidden rounded-lg border bg-white">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-2 w-16">Priority</th>
                    <th className="px-4 py-2">Name</th>
                    <th className="px-4 py-2">Conditions</th>
                    <th className="px-4 py-2">Action</th>
                    <th className="px-4 py-2">Active</th>
                    <th className="px-4 py-2"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {policies.map((p) => <PolicyRow key={p.id} p={p} />)}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {tab === 'violations' && <ViolationsTable />}
    </div>
  );
}

function PolicyRow({ p }: { p: PolicyDetail }) {
  const update = useUpdatePolicy(p.id);
  const remove = useDeletePolicy();
  const cond = Object.entries(p.conditions ?? {})
    .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join('|') : String(v)}`)
    .join(' · ');

  return (
    <tr className="hover:bg-slate-50">
      <td className="px-4 py-2 font-mono text-xs text-slate-600">{p.priority}</td>
      <td className="px-4 py-2">
        <div className="font-medium">{p.name}</div>
        {p.description && (
          <div className="mt-0.5 text-xs text-slate-500 line-clamp-2">{p.description}</div>
        )}
        {p.template_id && <div className="mt-0.5 text-xs text-slate-400">from {p.template_id}</div>}
      </td>
      <td className="px-4 py-2 text-xs text-slate-600 max-w-xs truncate">{cond || '(none)'}</td>
      <td className="px-4 py-2">
        <span className={ACTION_COLORS[p.action] ?? 'badge bg-slate-100'}>{p.action}</span>
      </td>
      <td className="px-4 py-2">
        <label className="inline-flex items-center">
          <input
            type="checkbox"
            checked={p.is_active}
            onChange={(e) => update.mutate({ is_active: e.target.checked })}
            className="rounded border-slate-300"
          />
        </label>
      </td>
      <td className="px-4 py-2 text-right">
        <button
          onClick={() => { if (confirm(`Delete policy "${p.name}"?`)) remove.mutate(p.id); }}
          className="rounded border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50"
        >
          Delete
        </button>
      </td>
    </tr>
  );
}

function ViolationsTable() {
  const { data, isLoading } = useViolations(false);

  if (isLoading) return <div className="text-sm text-slate-500">Loading…</div>;
  if (!data || data.length === 0) {
    return (
      <div className="rounded-lg border border-dashed bg-white p-12 text-center text-slate-500">
        <div className="font-medium">No unresolved violations</div>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border bg-white">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
          <tr>
            <th className="px-4 py-2">When</th>
            <th className="px-4 py-2">Action</th>
            <th className="px-4 py-2">System</th>
            <th className="px-4 py-2">Vector</th>
            <th className="px-4 py-2">Conditions matched</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {data.map((v: ViolationRow) => (
            <tr key={v.id}>
              <td className="px-4 py-2 text-xs text-slate-500">
                {new Date(v.occurred_at).toLocaleString()}
              </td>
              <td className="px-4 py-2">
                <span className={ACTION_COLORS[v.action_taken] ?? 'badge'}>{v.action_taken}</span>
              </td>
              <td className="px-4 py-2 text-xs text-slate-700 font-mono">
                {v.ai_system_id?.slice(0, 8) ?? '—'}
              </td>
              <td className="px-4 py-2 text-xs text-slate-600">{v.vector ?? '—'}</td>
              <td className="px-4 py-2 text-xs text-slate-600">
                {Array.isArray((v.violation_context as { matched_conditions?: string[] }).matched_conditions)
                  ? (v.violation_context as { matched_conditions: string[] }).matched_conditions.join(', ')
                  : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
