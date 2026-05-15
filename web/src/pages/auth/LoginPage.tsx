import { useState } from 'react';
import { sessionStore } from '@/lib/session';

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await sessionStore.login(username.trim(), password);
      // App.tsx subscribes to the session store and will swap to the dashboard.
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Login failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm space-y-4 rounded-lg border bg-white p-8 shadow-md"
      >
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded bg-brand-600" />
          <div>
            <div className="text-xl font-bold text-brand-700">AEGIS</div>
            <div className="text-xs text-slate-500">AI Enterprise Governance &amp; Inventory</div>
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium uppercase tracking-wide text-slate-500">
            Username
          </label>
          <input
            autoFocus
            required
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>

        <div>
          <label className="block text-xs font-medium uppercase tracking-wide text-slate-500">
            Password
          </label>
          <input
            required
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>

        {error && (
          <div className="rounded-md bg-red-50 p-2 text-xs text-red-700">{error}</div>
        )}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-60"
        >
          {busy ? 'Signing in…' : 'Sign in'}
        </button>

        <p className="text-center text-[11px] leading-relaxed text-slate-400">
          Authenticated by Keycloak. Your session ID rotates internally every few minutes;
          you stay signed in until you explicitly log out.
        </p>
      </form>
    </div>
  );
}
