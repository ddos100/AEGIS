import { NavLink, Route, Routes } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { useRegistryStats } from '@/hooks/useRegistry';
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
        {link('/settings', 'Settings')}
      </nav>
      <div className="mt-auto text-xs text-slate-400">v0.4.0 · Phase 4</div>
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
      <div className="mt-1 text-3xl font-bold">{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-400">{hint}</div>}
    </div>
  );
}

function Overview() {
  const { data: stats } = useRegistryStats();
  const critical = stats?.by_risk_level?.critical ?? 0;
  const high = stats?.by_risk_level?.high ?? 0;
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-brand-700">Overview</h1>
      <p className="max-w-2xl text-slate-600">
        AEGIS — your AI Security Posture Management platform. Phase 1 ships the AI System
        Registry and Service Catalogue. Discovery, risk scoring, and policy enforcement
        light up in subsequent phases.
      </p>

      <div className="grid gap-4 md:grid-cols-4">
        <StatCard label="AI systems"          value={stats?.total ?? '—'}            hint="Registry total" />
        <StatCard label="Shadow AI detected"  value={stats?.shadow_count ?? '—'}     hint="Auto-flagged, awaiting review" />
        <StatCard label="Critical + High"     value={`${critical + high}`}           hint={`${critical} critical · ${high} high`} />
        <StatCard label="Avg completeness"    value={stats ? `${stats.completeness_avg.toFixed(0)}%` : '—'} hint="ISO 42001 metadata coverage" />
      </div>

      {stats && stats.aisia_pending_count > 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <span className="font-semibold">{stats.aisia_pending_count}</span> system(s) need an AISIA — Phase 4 will trigger these automatically.
        </div>
      )}
    </div>
  );
}

function Placeholder({ title, phase }: { title: string; phase: string }) {
  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-bold text-brand-700">{title}</h1>
      <p className="text-slate-500">Coming in {phase}.</p>
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
            <Route path="/catalogue" element={<CatalogueBrowsePage />} />
            <Route path="/discovery" element={<DiscoveryPage />} />
            <Route path="/integrations" element={<IntegrationsPage />} />
            <Route path="/risk"        element={<RiskPage />} />
            <Route path="/aisia"       element={<AISIAListPage />} />
            <Route path="/aisia/:id"   element={<AISIAWizardPage />} />
            <Route path="/policy"      element={<PoliciesPage />} />
            <Route path="/compliance" element={<Placeholder title="Compliance" phase="Phase 5" />} />
            <Route path="/settings" element={<Placeholder title="Settings" phase="Phase 0" />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
