/**
 * Dashboard banner showing the AEGIS seed-data + recompute health.
 *
 * Hides itself when everything is green so the Overview page stays
 * uncluttered. Surfaces a one-click recovery (Reseed + Recompute now)
 * when any of the seed tables is empty — the single biggest "why is
 * everything blank?" cause.
 */
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';

interface SeedStatus {
  ok: boolean;
  counts: {
    ai_services:           number;
    threats:               number;
    compliance_frameworks: number;
    compliance_controls:   number;
    ai_systems:            number;
  };
  advice: string[];
  error?: string;
}

export default function SeedHealthBanner() {
  const { data } = useQuery<SeedStatus>({
    queryKey: ['admin', 'seed-status'],
    queryFn: async () => (await api.get<SeedStatus>('/admin/seed-status')).data,
    refetchInterval: 60_000,
    // 403 just means the user isn't analyst+ — quietly hide the banner.
    retry: false,
  });
  const qc = useQueryClient();
  const [busy, setBusy] = useState<'reseed' | 'recompute' | null>(null);

  // Quietly hide the banner if we couldn't fetch (e.g. viewer role).
  if (!data) return null;
  if (data.ok && data.counts.ai_systems > 0) return null;

  const onReseed = async () => {
    setBusy('reseed');
    try {
      const r = await api.post('/admin/reseed');
      qc.invalidateQueries({ queryKey: ['admin', 'seed-status'] });
      qc.invalidateQueries({ queryKey: ['threats'] });
      qc.invalidateQueries({ queryKey: ['systems'] });
      window.alert(`Reseed complete. See response in DevTools network tab:\n` +
                    JSON.stringify(r.data, null, 2).slice(0, 800));
    } catch (e) {
      window.alert(`Reseed failed: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  const onRecompute = async () => {
    setBusy('recompute');
    try {
      const r = await api.post('/admin/recompute-now');
      qc.invalidateQueries({ queryKey: ['exposures'] });
      qc.invalidateQueries({ queryKey: ['mitigations'] });
      qc.invalidateQueries({ queryKey: ['dashboard'] });
      window.alert(
        `Recompute fired:\n` +
        `  exposures.assessed = ${r.data.exposures?.assessed ?? '?'}\n` +
        `  risk.dispatched    = ${r.data.risk_recalc?.dispatched ?? '?'} ` +
        `(results land in 30-120s)`,
      );
    } catch (e) {
      window.alert(`Recompute failed: ${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  const hasEmptySeed = !data.ok;

  return (
    <div className={`rounded-lg border p-4 text-sm ${
      hasEmptySeed
        ? 'border-amber-300 bg-amber-50 text-amber-900'
        : 'border-slate-200 bg-slate-50 text-slate-700'
    }`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-semibold">
            {hasEmptySeed ? 'Platform seed data incomplete' : 'Platform ready — no AI systems yet'}
          </div>
          <div className="mt-1 flex flex-wrap gap-3 text-xs">
            <span>AI services: <b className="tabular-nums">{data.counts.ai_services}</b></span>
            <span>Threats: <b className="tabular-nums">{data.counts.threats}</b></span>
            <span>Frameworks: <b className="tabular-nums">{data.counts.compliance_frameworks}</b></span>
            <span>Controls: <b className="tabular-nums">{data.counts.compliance_controls}</b></span>
            <span>AI systems: <b className="tabular-nums">{data.counts.ai_systems}</b></span>
          </div>
          {data.advice.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-xs">
              {data.advice.map((line, i) => (<li key={i}>{line}</li>))}
            </ul>
          )}
          {!hasEmptySeed && data.counts.ai_systems === 0 && (
            <div className="mt-2 text-xs">
              Catalogue + threats are loaded but no AI systems have been observed in this
              tenant yet. Send network telemetry, install the Endpoint Agent, or
              <code className="mx-1 rounded bg-white px-1">+ Add system</code> manually
              from the Registry to populate Exposures and Mitigations.
            </div>
          )}
        </div>
        <div className="flex gap-2">
          {hasEmptySeed && (
            <button
              disabled={busy !== null}
              onClick={onReseed}
              className="rounded-md border border-amber-400 bg-white px-3 py-1.5 text-xs font-medium text-amber-800 hover:bg-amber-100 disabled:opacity-50"
            >
              {busy === 'reseed' ? 'Reseeding…' : 'Reseed now'}
            </button>
          )}
          <button
            disabled={busy !== null}
            onClick={onRecompute}
            className="rounded-md border border-brand-500 bg-white px-3 py-1.5 text-xs font-medium text-brand-700 hover:bg-brand-50 disabled:opacity-50"
          >
            {busy === 'recompute' ? 'Recomputing…' : 'Recompute now'}
          </button>
        </div>
      </div>
    </div>
  );
}
