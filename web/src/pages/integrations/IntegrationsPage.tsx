import { useState } from 'react';
import {
  useConnectorTypes,
  useCreateIntegration,
  useDeleteIntegration,
  useIntegrations,
  useSyncIntegration,
  useTestIntegration,
} from '@/hooks/useIntegrations';
import type { ConnectorInfo, IntegrationBrief, SyncRunResponse } from '@/types/integrations';

// Per-integration credential field hints. Drives the dynamic Add form.
const CREDENTIAL_HINTS: Record<string, { key: string; type: 'text' | 'password' | 'json'; placeholder: string }[]> = {
  entra_id: [
    { key: 'tenant_id',     type: 'text',     placeholder: 'Azure tenant UUID' },
    { key: 'client_id',     type: 'text',     placeholder: 'App registration client ID' },
    { key: 'client_secret', type: 'password', placeholder: 'App registration secret' },
  ],
  m365_copilot: [
    { key: 'tenant_id',     type: 'text',     placeholder: 'Azure tenant UUID' },
    { key: 'client_id',     type: 'text',     placeholder: 'App registration client ID' },
    { key: 'client_secret', type: 'password', placeholder: 'App registration secret' },
  ],
  okta: [
    { key: 'okta_domain',   type: 'text',     placeholder: 'your-org.okta.com' },
    { key: 'api_token',     type: 'password', placeholder: 'SSWS API token' },
  ],
  aws: [
    { key: 'regions',           type: 'text',     placeholder: 'comma-separated regions, e.g. us-east-1, ap-south-1' },
    { key: 'assume_role_arn',   type: 'text',     placeholder: 'arn:aws:iam::123456789012:role/AegisReadOnly (preferred)' },
    { key: 'external_id',       type: 'password', placeholder: 'STS external_id (optional)' },
    { key: 'access_key_id',     type: 'text',     placeholder: 'IAM user key (dev only)' },
    { key: 'secret_access_key', type: 'password', placeholder: 'IAM user secret (dev only)' },
  ],
};

function kindBadge(kind: string) {
  const cls = kind === 'idp' ? 'badge-medium' : kind === 'cloud' ? 'badge-low' : 'badge bg-indigo-100 text-indigo-800';
  return <span className={cls}>{kind}</span>;
}

function statusBadge(status: string) {
  if (status === 'active')   return <span className="badge-low">{status}</span>;
  if (status === 'error')    return <span className="badge-critical">{status}</span>;
  if (status === 'expired')  return <span className="badge-high">{status}</span>;
  return <span className="badge bg-slate-100 text-slate-600">{status}</span>;
}

function timeAgo(iso?: string | null) {
  if (!iso) return '—';
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 60)    return `${s|0}s ago`;
  if (s < 3600)  return `${s/60|0}m ago`;
  if (s < 86400) return `${s/3600|0}h ago`;
  return `${s/86400|0}d ago`;
}

export default function IntegrationsPage() {
  const { data: integrations, isLoading } = useIntegrations();
  const { data: types } = useConnectorTypes();
  const [addOpen, setAddOpen] = useState(false);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-brand-700">Integrations</h1>
          <p className="text-sm text-slate-600">
            Discovery sources for IdP OAuth grants, cloud AI control planes, and embedded SaaS AI usage.
            Credentials are Fernet-encrypted at rest and never returned by the API.
          </p>
        </div>
        <button
          onClick={() => setAddOpen(true)}
          className="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
        >
          + Add integration
        </button>
      </div>

      {isLoading && <div className="text-sm text-slate-500">Loading…</div>}

      {integrations && integrations.length === 0 && (
        <div className="rounded-lg border border-dashed bg-white p-12 text-center text-slate-500">
          <div className="font-medium">No integrations yet</div>
          <div className="mt-1 text-sm">Add one to start enumerating OAuth grants + cloud AI resources.</div>
        </div>
      )}

      {integrations && integrations.length > 0 && (
        <div className="overflow-hidden rounded-lg border bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2">Name</th>
                <th className="px-4 py-2">Integration</th>
                <th className="px-4 py-2">Kind</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Last sync</th>
                <th className="px-4 py-2">Last result</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {integrations.map((it) => <IntegrationRow key={it.id} it={it} />)}
            </tbody>
          </table>
        </div>
      )}

      {types && types.length > 0 && !isLoading && (
        <div className="text-xs text-slate-500">
          <b>Available connectors:</b>{' '}
          {types.map((t) => <code key={t.integration} className="mx-1 rounded bg-slate-100 px-1 py-0.5">{t.integration}</code>)}
        </div>
      )}

      {addOpen && types && (
        <AddIntegrationModal types={types} onClose={() => setAddOpen(false)} />
      )}
    </div>
  );
}

function IntegrationRow({ it }: { it: IntegrationBrief }) {
  const test    = useTestIntegration();
  const sync    = useSyncIntegration();
  const remove  = useDeleteIntegration();
  const [lastResult, setLastResult] = useState<SyncRunResponse | null>(null);

  const onTest = async () => setLastResult(await test.mutateAsync(it.id));
  const onSync = async () => setLastResult(await sync.mutateAsync(it.id));
  const onDelete = async () => {
    if (!confirm(`Delete integration "${it.name}"? This is irreversible.`)) return;
    await remove.mutateAsync(it.id);
  };

  return (
    <tr className="hover:bg-slate-50">
      <td className="px-4 py-2 font-medium">{it.name}</td>
      <td className="px-4 py-2 text-slate-700"><code>{it.integration}</code></td>
      <td className="px-4 py-2">{kindBadge(it.kind)}</td>
      <td className="px-4 py-2">{statusBadge(it.status)}</td>
      <td className="px-4 py-2 text-xs text-slate-500">{timeAgo(it.last_sync_at)}</td>
      <td className="px-4 py-2 text-xs">
        {lastResult ? (
          lastResult.ok
            ? <span className="text-green-700">✓ discovered {lastResult.discovered_count}, new {lastResult.new_count}</span>
            : <span className="text-red-700">✗ {lastResult.error}</span>
        ) : it.last_error
            ? <span className="text-red-700">{it.last_error.slice(0, 80)}{it.last_error.length > 80 ? '…' : ''}</span>
            : <span className="text-slate-400">—</span>
        }
      </td>
      <td className="px-4 py-2">
        <div className="flex gap-1 justify-end">
          <button
            onClick={onTest}
            disabled={test.isPending}
            className="rounded border border-slate-300 bg-white px-2 py-1 text-xs hover:bg-slate-50 disabled:opacity-50"
          >Test</button>
          <button
            onClick={onSync}
            disabled={sync.isPending}
            className="rounded border border-brand-500 bg-white px-2 py-1 text-xs text-brand-700 hover:bg-brand-50 disabled:opacity-50"
          >Sync</button>
          <button
            onClick={onDelete}
            className="rounded border border-red-300 bg-white px-2 py-1 text-xs text-red-700 hover:bg-red-50"
          >Delete</button>
        </div>
      </td>
    </tr>
  );
}

function AddIntegrationModal({ types, onClose }: { types: ConnectorInfo[]; onClose: () => void }) {
  const create = useCreateIntegration();
  const [integration, setIntegration] = useState(types[0]?.integration || '');
  const [name, setName] = useState('');
  const [fields, setFields] = useState<Record<string, string>>({});
  const hints = CREDENTIAL_HINTS[integration] || [];

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    // For AWS regions we want a list, not a string
    const credentials: Record<string, unknown> = { ...fields };
    if (integration === 'aws' && fields.regions) {
      credentials.regions = fields.regions.split(',').map(s => s.trim()).filter(Boolean);
    }
    await create.mutateAsync({ integration, name, credentials });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4" onClick={onClose}>
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={onSubmit}
        className="w-full max-w-lg space-y-3 rounded-lg bg-white p-6 shadow-xl"
      >
        <h2 className="text-lg font-semibold text-brand-700">Add integration</h2>

        <label className="block">
          <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Type</span>
          <select
            value={integration}
            onChange={(e) => { setIntegration(e.target.value); setFields({}); }}
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          >
            {types.map((t) => (
              <option key={t.integration} value={t.integration}>
                {t.integration} — {t.doc}
              </option>
            ))}
          </select>
        </label>

        <label className="block">
          <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Name</span>
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Prod Entra ID"
            className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
          />
        </label>

        {hints.length === 0 && (
          <div className="text-xs text-amber-700">
            No credential template for <code>{integration}</code> — credentials must be entered as JSON below.
          </div>
        )}

        {hints.map((h) => (
          <label key={h.key} className="block">
            <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{h.key}</span>
            <input
              type={h.type === 'password' ? 'password' : 'text'}
              value={fields[h.key] || ''}
              onChange={(e) => setFields(f => ({ ...f, [h.key]: e.target.value }))}
              placeholder={h.placeholder}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            />
          </label>
        ))}

        {create.isError && (
          <div className="rounded-md bg-red-50 p-2 text-xs text-red-700">
            {(create.error as Error).message}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" onClick={onClose}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50">
            Cancel
          </button>
          <button type="submit" disabled={create.isPending}
            className="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50">
            {create.isPending ? 'Saving…' : 'Create'}
          </button>
        </div>
      </form>
    </div>
  );
}
