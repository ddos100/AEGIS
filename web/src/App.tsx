import { NavLink, Link, Route, Routes } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { useDashboardOverview } from '@/hooks/useCompliance';
import EcosystemMap from '@/components/EcosystemMap';
import RegistryListPage from '@/pages/registry/RegistryListPage';
import RegistryDetailPage from '@/pages/registry/RegistryDetailPage';
import RegistryEditPage from '@/pages/registry/RegistryEditPage';
import CatalogueBrowsePage from '@/pages/catalogue/CatalogueBrowsePage';
import DiscoveryPage from '@/pages/discovery/DiscoveryPage';
import IntegrationsPage from '@/pages/integrations/IntegrationsPage';
import RiskPage from '@/pages/risk/RiskPage';
import AISIAListPage from '@/pages/aisia/AISIAListPage';
import AISIAWizardPage from '@/pages/aisia/AISIAWizardPage';
import PoliciesPage from '@/pages/policies/PoliciesPage';
import CompliancePage from '@/pages/compliance/CompliancePage';
import ReportsPage from '@/pages/reports/ReportsPage';

function Sidebar() {
  const link = (to: string, label: string, end = false) =>
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `block rounded-md px-3 py-2 text-sm font-medium ${
          isActive ? 'bg-brand-600 text-white' : 'text-slate-700 hover:bg-slate-200'
        }`
      }
    >{label}</NavLink>;

  return (
    <aside className="flex h-full w-60 flex-col gap-1 border-r bg-white p-4">
      <div className="mb-6 flex items-center gap-2">
        <div className="h-8 w-8 rounded bg-brand-600" />
        <div className="font-bold tracking-tight text-brand-700">AEGIS</div>
      </div>
      <nav className="flex flex-col gap-1">
        {link('/', 'Overview', true)}
        {link('/registry', 'AI Registry')}
        {link('/catalogue', 'Catalogue')}
        {link('/discovery', 'Discovery')}
        {link('/integrations', 'Integrations')}
        {link('/risk', 'Risk')}
        {link('/aisia', 'AISIA')}
        {link('/policy', 'Policies')}
        {link('/compliance', 'Compliance')}
        {link('/reports', 'Reports')}
      </nav>
      <div className="mt-auto text-xs text-slate-400">v0.5.0 · Phase 5</div>
    </aside>
  );
}

function HealthBadge() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['health'],
    queryFn: async () => (await api.get('/health')).data,
    refetchInterval: 10_000,
  });
  if (isLoading) return <span className="badge bg-slate-100 text-slate-700">checking…</span>;
  if (isError) return <span className="badge-critical">API down</span>;
  const ok = data?.status === 'ok';
  return <span className={ok ? 'badge-low' : 'badge-medium'}>API: {data?.status}</span>;
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

function Overview() {
  const { data, isLoading } = useDashboardOverview();
  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-brand-700">Overview</h1>
          <p className="text-sm text-slate-600 max-w-2xl">
            Live posture across the AEGIS stack — Discovery, Risk, AISIA, Policy, Compliance.
            Numbers refresh every minute.
          </p>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <StatCard label="AI systems"      value={data?.total_systems ?? '—'} hint="Registry total" />
        <StatCard label="Shadow AI"        value={data?.shadow_count ?? '—'}  hint="Auto-flagged" />
        <StatCard label="Critical + High"  value={data ? data.critical_count + data.high_count : '—'}
                  hint={data ? `${data.critical_count} critical · ${data.high_count} high` : ''} />
        <StatCard label="Risk posture"     value={data ? `${data.risk_posture_score}/100` : '—'}
                  hint="Weighted avg" />
      </div>

      {data && (data.aisia_pending_count > 0 || data.violations_open > 0) && (
        <div className="grid gap-3 md:grid-cols-2">
          {data.aisia_pending_count > 0 && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
              <Link to="/aisia" className="font-semibold hover:underline">
                {data.aisia_pending_count} AISIA pending →
              </Link>
              <div className="mt-0.5 text-xs">High/Critical systems auto-trigger an assessment.</div>
            </div>
          )}
          {data.violations_open > 0 && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-900">
              <Link to="/policy" className="font-semibold hover:underline">
                {data.violations_open} open policy violations →
              </Link>
            </div>
          )}
        </div>
      )}

      <section className="rounded-lg border bg-white p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold text-brand-700">AI Ecosystem Map</h2>
          <Link to="/discovery" className="text-xs text-brand-600 hover:underline">View discovery →</Link>
        </div>
        <EcosystemMap height={420} />
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-lg border bg-white">
          <header className="border-b px-4 py-2 flex items-center justify-between">
            <h2 className="font-semibold text-brand-700">Top risk systems</h2>
            <Link to="/risk" className="text-xs text-brand-600 hover:underline">All →</Link>
          </header>
          <table className="w-full text-sm">
            <tbody className="divide-y divide-slate-100">
              {(data?.top_risks ?? []).map((r) => (
                <tr key={r.id}>
                  <td className="px-4 py-2">
                    <Link to={`/registry/${r.id}`} className="font-medium text-brand-700 hover:underline">
                      {r.name}
                    </Link>
                    {r.is_shadow && <span className="ml-2 badge-shadow">Shadow</span>}
                    <div className="text-xs text-slate-500">{r.category}</div>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <span className={r.level === 'critical' ? 'badge-critical' :
                                     r.level === 'high'     ? 'badge-high' :
                                     r.level === 'medium'   ? 'badge-medium' : 'badge-low'}>
                      {r.level?.toUpperCase()} {r.score}
                    </span>
                  </td>
                </tr>
              ))}
              {data && data.top_risks.length === 0 && (
                <tr><td className="px-4 py-6 text-center text-slate-500" colSpan={2}>
                  No scored systems yet. Run risk recalc.
                </td></tr>
              )}
            </tbody>
          </table>
        </section>

        <section className="rounded-lg border bg-white">
          <header className="border-b px-4 py-2 flex items-center justify-between">
            <h2 className="font-semibold text-brand-700">Compliance coverage</h2>
            <Link to="/compliance" className="text-xs text-brand-600 hover:underline">Details →</Link>
          </header>
          <table className="w-full text-sm">
            <tbody className="divide-y divide-slate-100">
              {(data?.framework_scores ?? []).map((f) => (
                <tr key={f.slug}>
                  <td className="px-4 py-2">{f.name}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{f.score_pct}%</td>
                  <td className="px-4 py-2 w-1/2">
                    <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                      <div className="h-full bg-brand-500" style={{ width: `${f.score_pct}%` }} />
                    </div>
                  </td>
                </tr>
              ))}
              {data && data.framework_scores.length === 0 && (
                <tr><td className="px-4 py-6 text-center text-slate-500" colSpan={3}>
                  No frameworks imported yet — <code>make framework-import</code>
                </td></tr>
              )}
            </tbody>
          </table>
        </section>
      </div>

      {!data && isLoading && <div className="text-sm text-slate-500">Loading dashboard…</div>}
    </div>
  );
}

export default function App() {
  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <header className="flex items-center justify-between border-b bg-white px-6 py-3">
          <div className="text-sm text-slate-500">Securisti Consulting LLP · CONFIDENTIAL</div>
          <HealthBadge />
        </header>
        <div className="p-8">
          <Routes>
            <Route path="/" element={<Overview />} />
            <Route path="/registry" element={<RegistryListPage />} />
            <Route path="/registry/new" element={<RegistryEditPage />} />
            <Route path="/registry/:id" element={<RegistryDetailPage />} />
            <Route path="/registry/:id/edit" element={<RegistryEditPage />} />
            <Route path="/catalogue"   element={<CatalogueBrowsePage />} />
            <Route path="/discovery"   element={<DiscoveryPage />} />
            <Route path="/integrations" element={<IntegrationsPage />} />
            <Route path="/risk"        element={<RiskPage />} />
            <Route path="/aisia"       element={<AISIAListPage />} />
            <Route path="/aisia/:id"   element={<AISIAWizardPage />} />
            <Route path="/policy"      element={<PoliciesPage />} />
            <Route path="/compliance"  element={<CompliancePage />} />
            <Route path="/reports"     element={<ReportsPage />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
