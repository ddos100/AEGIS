import { Link, useNavigate, useParams } from 'react-router-dom';
import { useArchiveSystem, useSystem } from '@/hooks/useRegistry';
import { CompletenessBar, RiskBadge } from '@/components/RiskBadge';

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-0.5 text-sm text-slate-800">{value || <span className="text-slate-400">—</span>}</div>
    </div>
  );
}

export default function RegistryDetailPage() {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const { data, isLoading, isError } = useSystem(id);
  const archive = useArchiveSystem();

  if (isLoading) return <div className="text-sm text-slate-500">Loading…</div>;
  if (isError || !data) return <div className="text-sm text-red-600">System not found.</div>;

  const onArchive = async () => {
    if (!confirm(`Archive "${data.name}"? Status will be set to decommissioned.`)) return;
    await archive.mutateAsync(data.id);
    nav('/registry');
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link to="/registry" className="text-xs text-slate-500 hover:text-brand-600">← Registry</Link>
          <h1 className="mt-1 text-2xl font-bold text-brand-700">{data.name}</h1>
          {data.internal_alias && (
            <div className="text-sm text-slate-500">Internal alias: {data.internal_alias}</div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <RiskBadge level={data.risk_level} score={data.current_risk_score} />
          {data.is_shadow && <span className="badge-shadow">Shadow AI</span>}
          <Link
            to={`/registry/${data.id}/edit`}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Edit
          </Link>
          <button
            onClick={onArchive}
            className="rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50"
          >
            Archive
          </button>
        </div>
      </div>

      <div className="rounded-lg border bg-white p-4">
        <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
          Completeness ({data.completeness_score}%)
        </div>
        <CompletenessBar value={data.completeness_score} />
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-3 font-semibold text-brand-700">Classification</h2>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Category" value={data.category} />
            <Field label="Subcategory" value={data.subcategory} />
            <Field label="Deployment" value={data.deployment_type} />
            <Field label="Environment" value={data.deployment_env} />
            <Field label="EU AI Act" value={data.eu_ai_act_category} />
            <Field label="Status" value={data.status} />
          </div>
        </section>

        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-3 font-semibold text-brand-700">ISO 42001 — Purpose & Data</h2>
          <div className="space-y-3">
            <Field label="Intended purpose" value={data.intended_purpose} />
            <Field label="User population" value={data.user_population} />
            <Field label="Data types" value={data.data_types_processed.join(', ')} />
            <Field label="Affected subjects" value={data.affected_data_subjects.join(', ')} />
            <Field label="Output type" value={data.output_type} />
            <Field label="Human oversight" value={data.human_oversight_desc} />
            <Field label="Geographic scope" value={data.geographic_scope.join(', ')} />
          </div>
        </section>

        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-3 font-semibold text-brand-700">Discovery</h2>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Discovery sources" value={data.discovery_sources.join(', ')} />
            <Field label="First discovered" value={data.first_discovered_at && new Date(data.first_discovered_at).toLocaleString()} />
            <Field label="Last seen" value={data.last_seen_at && new Date(data.last_seen_at).toLocaleString()} />
            <Field label="Provider" value={data.provider_name_freetext || data.provider_id} />
          </div>
        </section>

        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-3 font-semibold text-brand-700">Risk & Compliance</h2>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Risk score" value={data.current_risk_score} />
            <Field label="Risk level" value={data.risk_level} />
            <Field label="Last assessed" value={data.last_risk_assessed_at && new Date(data.last_risk_assessed_at).toLocaleString()} />
            <Field label="AISIA status" value={data.aisia_status} />
            <Field label="AISIA impact" value={data.aisia_impact_level} />
            <Field label="Policy status" value={data.policy_status} />
          </div>
        </section>
      </div>

      {data.notes && (
        <section className="rounded-lg border bg-white p-4">
          <h2 className="mb-2 font-semibold text-brand-700">Notes</h2>
          <p className="whitespace-pre-wrap text-sm text-slate-700">{data.notes}</p>
        </section>
      )}
    </div>
  );
}
