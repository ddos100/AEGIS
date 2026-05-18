import { useMemo, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import {
  publishDraft,
  refreshFeeds,
  rejectDraft,
  useFeedSources,
  usePendingDrafts,
  type DraftBrief,
  type DraftDetail,
  type IngestRunResult,
} from '@/hooks/useThreats';

function sevBadge(s: DraftBrief['severity']) {
  return s === 'critical' ? 'badge-critical'
       : s === 'high'     ? 'badge-high'
       : s === 'medium'   ? 'badge-medium'
       : 'badge-low';
}

export default function ThreatFeedReviewPage() {
  const { data, isLoading, isError, error } = usePendingDrafts();
  const { data: sources } = useFeedSources();
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState<IngestRunResult[] | null>(null);
  const [editor, setEditor] = useState<{ id: string; body: string } | null>(null);

  const notLicensed = (error as { response?: { status?: number } })?.response?.status === 402;

  const onRefresh = async () => {
    setRunning(true);
    try {
      const r = await refreshFeeds();
      setLastRun(r);
      qc.invalidateQueries({ queryKey: ['threat-feed'] });
    } finally {
      setRunning(false);
    }
  };

  const onReject = async (id: string) => {
    const notes = window.prompt('Reason for rejection? (recorded on the draft)') || undefined;
    setBusy(id);
    try {
      await rejectDraft(id, notes);
      qc.invalidateQueries({ queryKey: ['threat-feed'] });
    } finally { setBusy(null); }
  };

  const openEditor = async (d: DraftBrief) => {
    setBusy(d.id);
    try {
      const detail = (await api.get<DraftDetail>(`/threats/feed/drafts/${d.id}`)).data;
      setEditor({ id: d.id, body: JSON.stringify(detail.draft, null, 2) });
    } catch (e) {
      window.alert(`Failed to load draft: ${(e as Error).message}`);
    } finally { setBusy(null); }
  };

  const onPublishFromEditor = async () => {
    if (!editor) return;
    let parsed: Record<string, unknown>;
    try { parsed = JSON.parse(editor.body); }
    catch (e) { window.alert(`Invalid JSON: ${(e as Error).message}`); return; }
    setBusy(editor.id);
    try {
      await publishDraft(editor.id, { edited_draft: parsed });
      qc.invalidateQueries({ queryKey: ['threat-feed'] });
      qc.invalidateQueries({ queryKey: ['threats'] });
      setEditor(null);
    } catch (e) {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      window.alert(`Publish failed: ${detail ?? (e as Error).message}`);
    } finally { setBusy(null); }
  };

  const pendingDrafts = useMemo(
    () => (data?.items ?? []).filter(d => d.review_status === 'pending_review'),
    [data],
  );
  const superseded = useMemo(
    () => (data?.items ?? []).filter(d => d.review_status === 'superseded'),
    [data],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-brand-700">Threat feed review</h1>
          <p className="mt-1 max-w-3xl text-sm text-slate-600">
            Drafts produced by the threat-feed ingest pipeline. The pipeline pulls every
            registered upstream source (MITRE ATLAS, OSV.dev, AI Incident Database, …)
            hourly and writes a candidate record here. Reviewers approve or reject
            before the entry becomes part of the canonical AEGIS catalogue.
          </p>
        </div>
        <button
          onClick={onRefresh}
          disabled={running}
          className="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {running ? 'Refreshing…' : 'Refresh feeds now'}
        </button>
      </div>

      {notLicensed && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <code>AEGIS-THREAT</code> not licensed. Contact licensing@securisti.com.
        </div>
      )}

      {sources && sources.length > 0 && (
        <section className="rounded-lg border bg-white p-3">
          <header className="text-xs font-medium uppercase tracking-wide text-slate-500">
            Registered feed sources
          </header>
          <div className="mt-1 flex flex-wrap gap-1">
            {sources.map(s => (
              <code key={s.source} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-brand-700">
                {s.source}
              </code>
            ))}
          </div>
        </section>
      )}

      {lastRun && (
        <section className="rounded-md border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900">
          <header className="font-medium">Last refresh result</header>
          <ul className="mt-1 space-y-0.5 text-xs">
            {lastRun.map((r) => (
              <li key={r.source} className="font-mono">
                {r.source}: {r.ok ? '✓' : '✗'} seen={r.seen} drafted={r.drafted} dup={r.duplicates} skip={r.skipped} err={r.errored}{r.error && ` — ${r.error}`}
              </li>
            ))}
          </ul>
        </section>
      )}

      {data && (
        <>
          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-lg border bg-white p-4">
              <div className="text-xs text-slate-500">Pending review</div>
              <div className="mt-1 text-3xl font-bold tabular-nums">{pendingDrafts.length}</div>
            </div>
            <div className="rounded-lg border bg-white p-4">
              <div className="text-xs text-slate-500">Superseded (re-review)</div>
              <div className="mt-1 text-3xl font-bold tabular-nums">{superseded.length}</div>
            </div>
            <div className="rounded-lg border bg-white p-4">
              <div className="text-xs text-slate-500">Total drafts in queue</div>
              <div className="mt-1 text-3xl font-bold tabular-nums">{data.total}</div>
            </div>
          </div>

          {isLoading && <div className="text-sm text-slate-500">Loading…</div>}

          {data.items.length === 0 && !isLoading && (
            <div className="rounded-lg border border-dashed bg-white p-12 text-center text-slate-500">
              <div className="font-medium">No drafts to review</div>
              <p className="mt-1 text-sm">
                Click <b>Refresh feeds now</b> to pull every registered source, or wait
                for the hourly beat schedule.
              </p>
            </div>
          )}

          {data.items.length > 0 && (
            <div className="overflow-hidden rounded-lg border bg-white">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-2 w-32">Source</th>
                    <th className="px-4 py-2 w-44">Threat ID</th>
                    <th className="px-4 py-2">Title</th>
                    <th className="px-4 py-2 w-20">Severity</th>
                    <th className="px-4 py-2 w-32">Status</th>
                    <th className="px-4 py-2 w-40 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {data.items.map((d) => (
                    <tr key={d.id} className="hover:bg-slate-50">
                      <td className="px-4 py-2 align-top">
                        <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-brand-700">
                          {d.source}
                        </code>
                      </td>
                      <td className="px-4 py-2 align-top">
                        <code className="font-mono text-xs text-slate-800">{d.threat_id}</code>
                      </td>
                      <td className="px-4 py-2 align-top">
                        <div className="font-medium text-slate-800">{d.title}</div>
                        <div className="mt-1 flex flex-wrap gap-1">
                          {d.classes.map((c) => (
                            <span key={c} className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700">{c}</span>
                          ))}
                          {d.vectors.map((v) => (
                            <span key={v} className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] text-indigo-700">{v}</span>
                          ))}
                        </div>
                      </td>
                      <td className="px-4 py-2 align-top">
                        <span className={sevBadge(d.severity)}>{d.severity}</span>
                      </td>
                      <td className="px-4 py-2 align-top">
                        <span className={d.review_status === 'pending_review'
                          ? 'badge bg-amber-100 text-amber-800'
                          : 'badge bg-blue-100 text-blue-800'}>
                          {d.review_status.replace('_', ' ')}
                        </span>
                      </td>
                      <td className="px-4 py-2 align-top text-right">
                        <div className="flex justify-end gap-1">
                          <button
                            disabled={busy === d.id}
                            onClick={() => openEditor(d)}
                            className="rounded border border-emerald-300 bg-white px-2 py-1 text-xs text-emerald-700 hover:bg-emerald-50 disabled:opacity-50"
                          >
                            Edit + Publish
                          </button>
                          <button
                            disabled={busy === d.id}
                            onClick={() => onReject(d.id)}
                            className="rounded border border-red-300 bg-white px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-50"
                          >
                            Reject
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {editor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
             onClick={() => setEditor(null)}>
          <div className="w-full max-w-3xl rounded-lg bg-white p-6 shadow-xl"
               onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold text-brand-700">Edit draft before publish</h2>
            <p className="mt-1 text-xs text-slate-500">
              Draft is shown verbatim as JSON. Edit any field — required: <code>threat_id</code>,
              <code className="ml-1">title</code>, <code>source_ref</code>,
              <code className="ml-1">verbatim_description</code>, <code>severity</code>,
              <code className="ml-1">classes</code>, <code>vectors</code>, and a non-empty
              <code className="ml-1">exposure_check</code>.
            </p>
            <textarea
              value={editor.body}
              onChange={(e) => setEditor({ ...editor, body: e.target.value })}
              spellCheck={false}
              className="mt-3 h-96 w-full rounded-md border border-slate-300 p-3 font-mono text-xs"
            />
            <div className="mt-3 flex justify-end gap-2">
              <button onClick={() => setEditor(null)}
                      className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50">
                Cancel
              </button>
              <button onClick={onPublishFromEditor}
                      disabled={busy === editor.id}
                      className="rounded bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50">
                {busy === editor.id ? 'Publishing…' : 'Publish'}
              </button>
            </div>
          </div>
        </div>
      )}

      {isError && !notLicensed && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          Failed to load drafts: {(error as Error).message}
        </div>
      )}
    </div>
  );
}
