import { useRiskSummary } from '@/hooks/useRiskPolicy';

const LEVELS = ['critical', 'high', 'medium', 'low'] as const;
const LEVEL_COLORS: Record<string, string> = {
  critical: 'bg-red-100 text-red-800',
  high:     'bg-orange-100 text-orange-800',
  medium:   'bg-yellow-100 text-yellow-800',
  low:      'bg-green-100 text-green-800',
};

const DRIVER_LABELS: Record<string, string> = {
  data_sensitivity:    'Data sensitivity',
  ai_capability:       'AI capability',
  regulatory_exposure: 'Regulatory exposure',
  access_scope:        'Access scope',
  provider_trust:      'Provider trust',
};

export default function RiskPage() {
  const { data, isLoading } = useRiskSummary();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-brand-700">Risk Posture</h1>
        <p className="text-sm text-slate-600">
          5-dimension scoring across the AI System Registry. Each system is reassessed daily;
          Critical / High systems get a Claude-generated risk narrative + an auto-triggered AISIA.
        </p>
      </div>

      {isLoading && <div className="text-sm text-slate-500">Loading…</div>}

      {data && (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            <StatCard label="Total systems" value={data.total_systems} />
            <StatCard label="Avg risk score" value={`${data.avg_score}/100`}
                      hint="Weighted across all systems" />
            <StatCard label="Critical + High"
                      value={(data.by_level.critical ?? 0) + (data.by_level.high ?? 0)}
                      hint="Require AISIA + risk narrative" />
            <StatCard label="Avg top driver" value={data.top_drivers[0]?.avg ?? '—'}
                      hint={DRIVER_LABELS[data.top_drivers[0]?.name] ?? '—'} />
          </div>

          <section className="rounded-lg border bg-white">
            <header className="border-b px-4 py-2">
              <h2 className="font-semibold text-brand-700">Risk-level distribution</h2>
            </header>
            <div className="grid grid-cols-2 gap-4 p-4 md:grid-cols-4">
              {LEVELS.map((lvl) => {
                const count = data.by_level[lvl] ?? 0;
                const pct = data.total_systems > 0
                  ? Math.round((count / data.total_systems) * 100) : 0;
                return (
                  <div key={lvl} className="rounded border p-3">
                    <div className="flex items-center justify-between">
                      <span className={`badge ${LEVEL_COLORS[lvl]}`}>{lvl.toUpperCase()}</span>
                      <span className="text-xs text-slate-500">{pct}%</span>
                    </div>
                    <div className="mt-2 text-3xl font-bold tabular-nums">{count}</div>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="rounded-lg border bg-white">
            <header className="border-b px-4 py-2">
              <h2 className="font-semibold text-brand-700">Top risk drivers (org-wide)</h2>
            </header>
            <div className="p-4 space-y-3">
              {data.top_drivers.map((d) => (
                <div key={d.name}>
                  <div className="flex justify-between text-sm">
                    <span className="font-medium">{DRIVER_LABELS[d.name] ?? d.name}</span>
                    <span className="tabular-nums text-slate-600">{d.avg}</span>
                  </div>
                  <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full bg-brand-600" style={{ width: `${d.avg}%` }} />
                  </div>
                </div>
              ))}
            </div>
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
      <div className="mt-1 text-3xl font-bold">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-400">{hint}</div>}
    </div>
  );
}
