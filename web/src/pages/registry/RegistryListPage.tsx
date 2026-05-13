import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useSystems } from '@/hooks/useRegistry';
import { CompletenessBar, RiskBadge } from '@/components/RiskBadge';

export default function RegistryListPage() {
  const [q, setQ] = useState('');
  const [shadowOnly, setShadowOnly] = useState(false);
  const [page, setPage] = useState(1);

  const { data, isLoading, isError } = useSystems({
    q: q || undefined,
    is_shadow: shadowOnly || undefined,
    page,
    per_page: 25,
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-brand-700">AI System Registry</h1>
        <div className="flex gap-2">
          <Link
            to="/catalogue"
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Browse Catalogue
          </Link>
          <Link
            to="/registry/new"
            className="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
          >
            + Add system
          </Link>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-lg border bg-white p-3">
        <input
          type="search"
          placeholder="Search by name, alias, or purpose…"
          value={q}
          onChange={(e) => { setQ(e.target.value); setPage(1); }}
          className="flex-1 min-w-[260px] rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={shadowOnly}
            onChange={(e) => { setShadowOnly(e.target.checked); setPage(1); }}
            className="rounded border-slate-300"
          />
          Shadow AI only
        </label>
        {data && (
          <span className="ml-auto text-xs text-slate-500">
            {data.total} system{data.total === 1 ? '' : 's'}
          </span>
        )}
      </div>

      {isLoading && <div className="text-sm text-slate-500">Loading…</div>}
      {isError && <div className="text-sm text-red-600">Failed to load registry.</div>}

      {data && data.items.length === 0 && (
        <div className="rounded-lg border border-dashed bg-white p-12 text-center text-slate-500">
          <div className="font-medium">No AI systems yet</div>
          <div className="mt-1 text-sm">
            Add one manually, or import from the{' '}
            <Link to="/catalogue" className="text-brand-600 underline">catalogue</Link>.
          </div>
        </div>
      )}

      {data && data.items.length > 0 && (
        <div className="overflow-hidden rounded-lg border bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2">Category</th>
                <th className="px-4 py-2">Risk</th>
                <th className="px-4 py-2">Completeness</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Shadow</th>
                <th className="px-4 py-2">Last seen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.items.map((s) => (
                <tr key={s.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2">
                    <Link to={`/registry/${s.id}`} className="font-medium text-brand-700 hover:underline">
                      {s.name}
                    </Link>
                    {s.provider_slug && <div className="text-xs text-slate-500">{s.provider_slug}</div>}
                  </td>
                  <td className="px-4 py-2 text-slate-700">{s.category}</td>
                  <td className="px-4 py-2"><RiskBadge level={s.risk_level} score={s.current_risk_score} /></td>
                  <td className="px-4 py-2"><CompletenessBar value={s.completeness_score} /></td>
                  <td className="px-4 py-2 text-slate-700">{s.status}</td>
                  <td className="px-4 py-2">
                    {s.is_shadow ? <span className="badge-shadow">Shadow</span> : <span className="text-slate-400">—</span>}
                  </td>
                  <td className="px-4 py-2 text-slate-500">
                    {s.last_seen_at ? new Date(s.last_seen_at).toLocaleDateString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {data.pages > 1 && (
            <div className="flex items-center justify-between border-t bg-slate-50 px-4 py-2 text-xs text-slate-600">
              <div>Page {data.page} of {data.pages}</div>
              <div className="flex gap-2">
                <button
                  disabled={data.page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="rounded border border-slate-300 bg-white px-2 py-1 disabled:opacity-50"
                >
                  Prev
                </button>
                <button
                  disabled={data.page >= data.pages}
                  onClick={() => setPage((p) => p + 1)}
                  className="rounded border border-slate-300 bg-white px-2 py-1 disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
