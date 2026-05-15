import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useAISIA, useAISIADraft, useSubmitAISIA, useUpdateAISIA } from '@/hooks/useRiskPolicy';

type StepKey =
  | 'intended_purpose_confirmed'
  | 'affected_population'
  | 'severity_assessment'
  | 'reversibility_assessment'
  | 'human_oversight_assessment'
  | 'treatment_decision';

const STEPS: { key: StepKey; title: string; prompt: string }[] = [
  { key: 'intended_purpose_confirmed', title: 'Intended purpose',     prompt: 'Confirm what this AI system is used for and its legitimate basis.' },
  { key: 'affected_population',        title: 'Affected population',  prompt: 'Who is impacted by its outputs? How many people? Are any vulnerable?' },
  { key: 'severity_assessment',        title: 'Severity',             prompt: 'What harm can occur if the system fails, produces biased outputs, or is misused?' },
  { key: 'reversibility_assessment',   title: 'Reversibility',        prompt: 'Can harms be corrected? How quickly?' },
  { key: 'human_oversight_assessment', title: 'Human oversight',      prompt: 'Is there a human in the loop? What override or escalation mechanisms exist?' },
  { key: 'treatment_decision',         title: 'Treatment decision',   prompt: 'Choose: accept (with documented controls), restrict (limit users / data), or block.' },
];

export default function AISIAWizardPage() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading } = useAISIA(id);
  const update = useUpdateAISIA(id || '');
  const submit = useSubmitAISIA(id || '');
  const draftMut = useAISIADraft();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<Partial<Record<StepKey, string>>>({});
  const [draft, setDraft] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setForm({
        intended_purpose_confirmed: data.intended_purpose_confirmed ?? undefined,
        affected_population:        data.affected_population ?? undefined,
        severity_assessment:        data.severity_assessment ?? undefined,
        reversibility_assessment:   data.reversibility_assessment ?? undefined,
        human_oversight_assessment: data.human_oversight_assessment ?? undefined,
        treatment_decision:         data.treatment_decision ?? undefined,
      });
      setDraft(data.ai_draft);
    }
  }, [data]);

  if (isLoading || !data) return <div className="text-sm text-slate-500">Loading…</div>;

  const cur = STEPS[step];
  const handleSave = async () => {
    await update.mutateAsync({ [cur.key]: form[cur.key] ?? null, status: 'in_progress' });
  };
  const handleDraft = async () => {
    if (!id) return;
    const res = await draftMut.mutateAsync(id);
    setDraft(res.draft ?? res.fallback ?? null);
  };
  const handleSubmit = async () => {
    await handleSave();
    await submit.mutateAsync();
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Link to="/aisia" className="text-xs text-slate-500 hover:text-brand-600">← AISIA</Link>
          <h1 className="mt-1 text-2xl font-bold text-brand-700">AISIA Wizard</h1>
          <p className="text-xs text-slate-500">
            ISO 42001 Clause 6.1.2 — six-step AI System Impact Assessment.
            Status: <b>{data.status}</b>
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleDraft}
            disabled={draftMut.isPending}
            className="rounded-md border border-brand-500 px-3 py-1.5 text-xs font-medium text-brand-700 hover:bg-brand-50 disabled:opacity-50"
          >
            {draftMut.isPending ? 'Generating…' : draft ? 'Refresh AI draft' : 'Generate AI draft'}
          </button>
          {data.status !== 'approved' && (
            <button
              onClick={handleSubmit}
              disabled={submit.isPending}
              className="rounded-md bg-brand-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              Submit for review
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {STEPS.map((s, idx) => (
          <button
            key={s.key}
            onClick={() => setStep(idx)}
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              idx === step ? 'bg-brand-600 text-white' :
              form[s.key]  ? 'bg-green-100 text-green-800' :
                             'bg-slate-100 text-slate-600'
            }`}
          >
            {idx + 1}. {s.title}
          </button>
        ))}
      </div>

      <section className="rounded-lg border bg-white p-4">
        <h2 className="font-semibold text-brand-700">{cur.title}</h2>
        <p className="mt-1 text-sm text-slate-600">{cur.prompt}</p>
        <textarea
          rows={6}
          value={form[cur.key] ?? ''}
          onChange={(e) => setForm((f) => ({ ...f, [cur.key]: e.target.value }))}
          onBlur={handleSave}
          placeholder="Type your assessment here…"
          className="mt-3 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <div className="mt-3 flex justify-between">
          <button
            disabled={step === 0}
            onClick={() => setStep((s) => Math.max(0, s - 1))}
            className="rounded border border-slate-300 bg-white px-3 py-1 text-xs disabled:opacity-50"
          >
            ← Previous
          </button>
          <button
            disabled={step === STEPS.length - 1}
            onClick={() => setStep((s) => Math.min(STEPS.length - 1, s + 1))}
            className="rounded border border-slate-300 bg-white px-3 py-1 text-xs disabled:opacity-50"
          >
            Next →
          </button>
        </div>
      </section>

      {draft && (
        <section className="rounded-lg border border-brand-200 bg-brand-50 p-4">
          <h2 className="font-semibold text-brand-700">AI-generated draft</h2>
          <pre className="mt-2 whitespace-pre-wrap text-sm text-slate-800">{draft}</pre>
        </section>
      )}
    </div>
  );
}
