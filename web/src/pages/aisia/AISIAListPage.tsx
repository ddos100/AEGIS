import { Link } from 'react-router-dom';
import { useAISIAList } from '@/hooks/useRiskPolicy';

const STATUS_BADGES: Record<string, string> = {
  initiated:   'badge bg-slate-100 text-slate-700',
  in_progress: 'badge-medium',
  completed:   'badge bg-blue-100 text-blue-800',
  approved:    'badge-low',
  rejected:    'badge-critical',
};

export default function AISIAListPage() {
  const { data, isLoading } = useAISIAList();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-brand-700">AISIA Assessments</h1>
        <p className="text-sm text-slate-600">
          AI System Impact Assessments (ISO 42001 Clause 6.1.2). Critical and High-risk systems
          have one auto-initiated on every daily risk recalc.
        </p>
      </div>

      {isLoading && <div className="text-sm text-slate-500">Loading…</div>}

      {data && data.length === 0 && (
        <div className="rounded-lg border border-dashed bg-white p-12 text-center text-slate-500">
          <div className="font-medium">No AISIA records yet</div>
          <div className="mt-1 text-sm">
            Risk recalculation runs daily; Critical and High-risk systems will appear here.
            You can also initiate one manually from a Registry detail page.
          </div>
        </div>
      )}

      {data && data.length > 0 && (
        <div className="overflow-hidden rounded-lg border bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2">System</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2">Impact level</th>
                <th className="px-4 py-2">Treatment</th>
                <th className="px-4 py-2">Initiated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((a) => (
                <tr key={a.id} className="hover:bg-slate-50">
                  <td className="px-4 py-2">
                    <Link to={`/aisia/${a.id}`} className="text-brand-700 hover:underline font-medium">
                      {a.ai_system_id.slice(0, 8)}…
                    </Link>
                  </td>
                  <td className="px-4 py-2">
                    <span className={STATUS_BADGES[a.status] ?? 'badge bg-slate-100 text-slate-700'}>
                      {a.status}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-slate-600">{a.impact_level ?? '—'}</td>
                  <td className="px-4 py-2 text-slate-600">{a.treatment_decision ?? '—'}</td>
                  <td className="px-4 py-2 text-xs text-slate-500">
                    {new Date(a.initiated_at).toLocaleDateString()}
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
