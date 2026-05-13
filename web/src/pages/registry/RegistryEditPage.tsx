import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useCreateSystem, useSystem, useUpdateSystem } from '@/hooks/useRegistry';
import type { AISystemDetail } from '@/types/registry';

const CATEGORIES = [
  'llm', 'image_gen', 'video_gen', 'speech', 'code', 'search', 'recommendation',
  'classifier', 'embedding', 'agent', 'browser_extension', 'security_ai',
  'data_analytics', 'other',
];
const DATA_TYPES = [
  'personal', 'sensitive_personal', 'financial', 'health', 'biometric',
  'internal', 'public', 'intellectual_property', 'credentials', 'other',
];
const SUBJECTS = ['employees', 'customers', 'third_parties', 'public', 'minors', 'other'];
const DEPLOYMENT_TYPES = [
  'cloud_saas', 'cloud_api', 'on_premise', 'browser_extension', 'desktop_agent', 'embedded_saas',
];
const STATUSES = ['active', 'pilot', 'decommissioned', 'under_review'];
const EU_AI_ACT = ['unacceptable', 'high_risk', 'limited_risk', 'minimal_risk', 'general_purpose_ai'];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border bg-white p-4">
      <h2 className="mb-3 font-semibold text-brand-700">{title}</h2>
      <div className="grid gap-3 md:grid-cols-2">{children}</div>
    </section>
  );
}

function FieldLabel({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}{required && <span className="ml-0.5 text-red-500">*</span>}
      </span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

function CheckGroup({ value, onChange, options }: {
  value: string[];
  onChange: (v: string[]) => void;
  options: string[];
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((opt) => {
        const checked = value.includes(opt);
        return (
          <label
            key={opt}
            className={`cursor-pointer rounded-full border px-3 py-1 text-xs ${
              checked ? 'border-brand-500 bg-brand-50 text-brand-700' : 'border-slate-300 text-slate-600 hover:bg-slate-50'
            }`}
          >
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => onChange(e.target.checked ? [...value, opt] : value.filter((v) => v !== opt))}
              className="sr-only"
            />
            {opt}
          </label>
        );
      })}
    </div>
  );
}

export default function RegistryEditPage() {
  const { id } = useParams<{ id?: string }>();
  const isEdit = !!id && id !== 'new';
  const nav = useNavigate();
  const { data: existing, isLoading } = useSystem(isEdit ? id : undefined);

  const create = useCreateSystem();
  const update = useUpdateSystem(id || '');

  // Local form state with safe defaults.
  const [form, setForm] = useState<Partial<AISystemDetail>>(() => existing ?? {
    name: '',
    category: 'llm',
    deployment_type: 'cloud_saas',
    status: 'active',
    data_types_processed: [],
    affected_data_subjects: [],
    geographic_scope: [],
    tags: [],
    aisia_status: 'not_started',
  });

  // Sync local form when existing data arrives
  if (isEdit && existing && !form.id) {
    setForm(existing);
  }

  if (isEdit && isLoading) return <div className="text-sm text-slate-500">Loading…</div>;

  const set = <K extends keyof AISystemDetail>(key: K, value: AISystemDetail[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
  };

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const result = isEdit ? await update.mutateAsync(form) : await create.mutateAsync(form);
    nav(`/registry/${result.id}`);
  };

  const text = (key: keyof AISystemDetail, multiline = false) => {
    const v = (form[key] as string | null) ?? '';
    const className =
      'w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500';
    return multiline ? (
      <textarea
        rows={3}
        value={v}
        onChange={(e) => set(key, e.target.value as AISystemDetail[typeof key])}
        className={className}
      />
    ) : (
      <input
        type="text"
        value={v}
        onChange={(e) => set(key, e.target.value as AISystemDetail[typeof key])}
        className={className}
      />
    );
  };

  const select = (key: keyof AISystemDetail, options: string[], placeholder = '— select —') => (
    <select
      value={(form[key] as string | null) ?? ''}
      onChange={(e) => set(key, (e.target.value || null) as AISystemDetail[typeof key])}
      className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
    >
      <option value="">{placeholder}</option>
      {options.map((o) => <option key={o} value={o}>{o}</option>)}
    </select>
  );

  return (
    <form onSubmit={onSubmit} className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-brand-700">
          {isEdit ? 'Edit AI system' : 'Add AI system'}
        </h1>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => nav(-1)}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={create.isPending || update.isPending}
            className="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {isEdit ? 'Save changes' : 'Create'}
          </button>
        </div>
      </div>

      <Section title="Identity">
        <FieldLabel label="Name" required>{text('name')}</FieldLabel>
        <FieldLabel label="Internal alias">{text('internal_alias')}</FieldLabel>
        <FieldLabel label="Version">{text('version')}</FieldLabel>
        <FieldLabel label="Provider (free text)">{text('provider_name_freetext')}</FieldLabel>
      </Section>

      <Section title="Classification">
        <FieldLabel label="Category" required>{select('category', CATEGORIES, 'llm')}</FieldLabel>
        <FieldLabel label="Subcategory">{text('subcategory')}</FieldLabel>
        <FieldLabel label="Deployment type">{select('deployment_type', DEPLOYMENT_TYPES)}</FieldLabel>
        <FieldLabel label="Status">{select('status', STATUSES)}</FieldLabel>
        <FieldLabel label="EU AI Act category">{select('eu_ai_act_category', EU_AI_ACT)}</FieldLabel>
      </Section>

      <Section title="ISO 42001 — Purpose & Data">
        <FieldLabel label="Intended purpose">{text('intended_purpose', true)}</FieldLabel>
        <FieldLabel label="Actual use observed">{text('actual_use_observed', true)}</FieldLabel>
        <FieldLabel label="User population">{text('user_population')}</FieldLabel>
        <FieldLabel label="Output type">{text('output_type')}</FieldLabel>
        <div className="md:col-span-2">
          <FieldLabel label="Data types processed">
            <CheckGroup
              value={form.data_types_processed ?? []}
              onChange={(v) => set('data_types_processed', v)}
              options={DATA_TYPES}
            />
          </FieldLabel>
        </div>
        <div className="md:col-span-2">
          <FieldLabel label="Affected data subjects">
            <CheckGroup
              value={form.affected_data_subjects ?? []}
              onChange={(v) => set('affected_data_subjects', v)}
              options={SUBJECTS}
            />
          </FieldLabel>
        </div>
        <FieldLabel label="Human oversight description">{text('human_oversight_desc', true)}</FieldLabel>
        <FieldLabel label="Business unit">{text('business_unit')}</FieldLabel>
      </Section>

      <Section title="Notes">
        <div className="md:col-span-2">
          <FieldLabel label="Notes">{text('notes', true)}</FieldLabel>
        </div>
      </Section>
    </form>
  );
}
