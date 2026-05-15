import { useState } from 'react';
import { api } from '@/lib/api';
import {
  useFrameworks,
  useGenerateReport,
  useReports,
} from '@/hooks/useCompliance';

const REPORT_TYPES = [
  { value: 'executive_summary', label: 'Executive Summary' },
  { value: 'framework_audit',   label: 'Framework Audit' },
];

const STATUS_LABEL: Record<string, string> = {
  pending:    'badge bg-slate-100 text-slate-700',
  generating: 'badge-medium',
  ready:      'badge-low',
  failed:     'badge-critical',
};

export default function ReportsPage() {
  const { data: reports, isLoading } = useReports();
  const { data: frameworks } = useFrameworks();
  const generate = useGenerateReport();
  const [reportType, setReportType] = useState('executive_summary');
  const [frameworkId, setFrameworkId] = useState<string | ''>('');

  const onGenerate = async () => {
    await generate.mutateAsync({
      report_type: reportType,
      framework_id: reportType === 'framework_audit' ? (frameworkId || undefined) : undefined,
      file_format: 'pdf',
    });
  };

  const onDownload = async (id: string, fmt: string) => {
    const resp = await api.get(`/reports/${id}/download`, { responseType: 'blob' });
    const url = window.URL.createObjectURL(new Blob([resp.data]));
    const a = document.createElement('a');
    a.href = url;
    a.download = `aegis-${id}.${fmt}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-700">Reports</h1>
        <p className="text-sm text-slate-600">
          Executive summary + per-framework audit PDFs. WeasyPrint renders the templates inside the
          API container; if it can't load on a given host, the report is delivered as HTML and the
          download button serves that instead.
        </p>
      </div>

      <section className="rounded-lg border bg-white p-4">
        <div className="grid gap-3 md:grid-cols-3">
          <label className="block">
            <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Report type</span>
            <select
              value={reportType}
              onChange={(e) => setReportType(e.target.value)}
              className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            >
              {REPORT_TYPES.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
          </label>
          {reportType === 'framework_audit' && (
            <label className="block">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-500">Framework</span>
              <select
                value={frameworkId}
                onChange={(e) => setFrameworkId(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm"
              >
                <option value="">Select…</option>
                {frameworks?.map((f) => (
                  <option key={f.id} value={f.id}>{f.name}</option>
                ))}
              </select>
            </label>
          )}
          <div className="flex items-end">
            <button
              onClick={onGenerate}
              disabled={generate.isPending ||
                (reportType === 'framework_audit' && !frameworkId)}
              className="w-full rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {generate.isPending ? 'Generating…' : 'Generate report'}
            </button>
          </div>
        </div>
      </section>

      {isLoading && <div className="text-sm text-slate-500">Loading…</div>}

      {reports && reports.length === 0 && (
        <div className="rounded-lg border border-dashed bg-white p-12 text-center text-slate-500">
          <div className="font-medium">No reports yet</div>
          <div className="mt-1 text-sm">Generate one above to get started.</div>
        </div>
      )}

      {reports && reports.length > 0 && (
        <div className="overflow-hidden rounded-lg border bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2">Type</th>
                <th className="px-4 py-2">Format</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Size</th>
                <th className="px-4 py-2">Requested</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {reports.map((r) => (
                <tr key={r.id}>
                  <td className="px-4 py-2 font-medium">{r.report_type}</td>
                  <td className="px-4 py-2 uppercase text-xs">{r.file_format}</td>
                  <td className="px-4 py-2">
                    <span className={STATUS_LABEL[r.status] || 'badge'}>{r.status}</span>
                    {r.error && (
                      <div className="mt-0.5 text-xs text-red-600 truncate max-w-xs">{r.error}</div>
                    )}
                  </td>
                  <td className="px-4 py-2 tabular-nums">
                    {r.file_size_bytes ? `${(r.file_size_bytes / 1024).toFixed(1)} KB` : '—'}
                  </td>
                  <td className="px-4 py-2 text-xs text-slate-500">
                    {new Date(r.requested_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => onDownload(r.id, r.file_format)}
                      disabled={r.status !== 'ready'}
                      className="rounded border border-brand-500 bg-white px-3 py-1 text-xs text-brand-700 hover:bg-brand-50 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      Download
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
