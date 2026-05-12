import { NavLink, Route, Routes } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

function Sidebar() {
  const link = (to: string, label: string) =>
    <NavLink
      to={to}
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
        {link('/', 'Overview')}
        {link('/registry', 'AI Registry')}
        {link('/discovery', 'Discovery')}
        {link('/risk', 'Risk')}
        {link('/policy', 'Policies')}
        {link('/compliance', 'Compliance')}
        {link('/settings', 'Settings')}
      </nav>
      <div className="mt-auto text-xs text-slate-400">v0.1.0 · Phase 0</div>
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

function Overview() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-brand-700">Overview</h1>
      <p className="text-slate-600 max-w-2xl">
        Welcome to AEGIS — your AI Security Posture Management platform.
        This is the Phase 0 scaffold; the Discovery Engine, Registry, Risk and Policy modules
        will light up in subsequent phases.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {[
          { label: 'AI systems', value: '—', hint: 'Phase 1' },
          { label: 'Shadow AI detected', value: '—', hint: 'Phase 2' },
          { label: 'Critical-risk systems', value: '—', hint: 'Phase 4' },
        ].map((c) => (
          <div key={c.label} className="rounded-lg border bg-white p-4">
            <div className="text-sm text-slate-500">{c.label}</div>
            <div className="mt-1 text-3xl font-bold">{c.value}</div>
            <div className="mt-1 text-xs text-slate-400">{c.hint}</div>
          </div>
        ))}
      </div>
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
            <Route path="/registry" element={<Placeholder title="AI System Registry" phase="Phase 1" />} />
            <Route path="/discovery" element={<Placeholder title="Discovery" phase="Phase 2" />} />
            <Route path="/risk" element={<Placeholder title="Risk Assessment" phase="Phase 4" />} />
            <Route path="/policy" element={<Placeholder title="Policy Engine" phase="Phase 4" />} />
            <Route path="/compliance" element={<Placeholder title="Compliance" phase="Phase 5" />} />
            <Route path="/settings" element={<Placeholder title="Settings" phase="Phase 0" />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
