import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAddFromCatalogue, useCatalogueCategories, useCatalogueServices } from '@/hooks/useRegistry';

export default function CatalogueBrowsePage() {
  const nav = useNavigate();
  const [q, setQ] = useState('');
  const [category, setCategory] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [pending, setPending] = useState<string | null>(null);

  const { data: cats } = useCatalogueCategories();
  const { data, isLoading } = useCatalogueServices({ q: q || undefined, category, page, per_page: 30 });
  const add = useAddFromCatalogue();

  const onQuickAdd = async (catalogue_service_id: string) => {
    setPending(catalogue_service_id);
    try {
      const created = await add.mutateAsync({ catalogue_service_id });
      nav(`/registry/${created.id}/edit`);  // open the edit form so the user can fill ISO 42001 fields
    } finally {
      setPending(null);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-700">AI Service Catalogue</h1>
        <p className="mt-1 text-sm text-slate-600">
          Browse the curated catalogue and quick-add any service to your registry. The new record will
          be pre-populated from the catalogue entry — finish the ISO 42001 fields on the edit form.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-lg border bg-white p-3">
        <input
          type="search"
          placeholder="Search services…"
          value={q}
          onChange={(e) => { setQ(e.target.value); setPage(1); }}
          className="flex-1 min-w-[260px] rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <select
          value={category ?? ''}
          onChange={(e) => { setCategory(e.target.value || undefined); setPage(1); }}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        >
          <option value="">All categories</option>
          {cats?.map((c) => (
            <option key={c.category} value={c.category}>
              {c.category} ({c.count})
            </option>
          ))}
        </select>
        {data && (
          <span className="ml-auto text-xs text-slate-500">
            {data.total} match{data.total === 1 ? '' : 'es'}
          </span>
        )}
      </div>

      {isLoading && <div className="text-sm text-slate-500">Loading…</div>}

      {data && (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.items.map((s) => (
            <div key={s.id} className="flex flex-col rounded-lg border bg-white p-4">
              <div className="flex-1">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="font-semibold text-brand-700">{s.name}</div>
                    {s.provider_slug && <div className="text-xs text-slate-500">{s.provider_slug}</div>}
                  </div>
                  <span className="badge bg-slate-100 text-slate-700">{s.category}</span>
                </div>
                {s.description && (
                  <p className="mt-2 line-clamp-3 text-sm text-slate-600">{s.description}</p>
                )}
                {s.tags.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {s.tags.slice(0, 4).map((t) => (
                      <span key={t} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{t}</span>
                    ))}
                  </div>
                )}
              </div>
              <button
                onClick={() => onQuickAdd(s.id)}
                disabled={pending === s.id}
                className="mt-3 w-full rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
              >
                {pending === s.id ? 'Adding…' : '+ Add to registry'}
              </button>
            </div>
          ))}
        </div>
      )}

      {data && data.pages > 1 && (
        <div className="flex items-center justify-center gap-2 text-sm">
          <button
            disabled={data.page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="rounded border border-slate-300 bg-white px-3 py-1 disabled:opacity-50"
          >
            Prev
          </button>
          <span className="text-slate-600">Page {data.page} of {data.pages}</span>
          <button
            disabled={data.page >= data.pages}
            onClick={() => setPage((p) => p + 1)}
            className="rounded border border-slate-300 bg-white px-3 py-1 disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
