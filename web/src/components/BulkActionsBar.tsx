/**
 * Reusable bulk-selection toolbar.
 *
 * Stays sticky at the bottom of the viewport while at least one item
 * is selected. Renders the count + per-action buttons + Clear.
 *
 * Usage pattern:
 *   const sel = useBulkSelection<string>();
 *   <BulkActionsBar
 *     count={sel.count}
 *     onClear={sel.clear}
 *     actions={[
 *       { label: 'Reject',  onClick: handleBulkReject,  variant: 'danger' },
 *       { label: 'Approve', onClick: handleBulkApprove, variant: 'primary' },
 *     ]}
 *   />
 */
import type { ReactNode } from 'react';

export type BulkActionVariant = 'primary' | 'danger' | 'neutral' | 'emerald';

export interface BulkAction {
  label:    string;
  onClick:  () => void | Promise<void>;
  variant?: BulkActionVariant;
  disabled?: boolean;
  // Optional confirmation prompt shown via window.confirm before invoking.
  confirm?: string;
}

interface Props {
  count:    number;
  onClear:  () => void;
  actions:  BulkAction[];
  // Optional extra content rendered to the right of the action buttons,
  // e.g. a select-all toggle or a "n of m" count.
  trailing?: ReactNode;
}

const VARIANT_CLS: Record<BulkActionVariant, string> = {
  primary: 'border-brand-500 bg-white text-brand-700 hover:bg-brand-50',
  emerald: 'border-emerald-300 bg-white text-emerald-700 hover:bg-emerald-50',
  danger:  'border-red-300 bg-white text-red-700 hover:bg-red-50',
  neutral: 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50',
};

export default function BulkActionsBar({ count, onClear, actions, trailing }: Props) {
  if (count <= 0) return null;
  return (
    <div className="sticky bottom-3 z-40 mx-auto flex max-w-4xl items-center
                    gap-2 rounded-full border border-slate-300 bg-white px-4
                    py-2 text-sm shadow-lg">
      <span className="rounded-full bg-brand-600 px-2 py-0.5 text-xs font-medium text-white">
        {count} selected
      </span>
      {actions.map((a, i) => (
        <button
          key={i}
          disabled={a.disabled}
          onClick={async () => {
            if (a.confirm && !window.confirm(a.confirm)) return;
            await a.onClick();
          }}
          className={`rounded-md border px-3 py-1 text-xs font-medium
                      disabled:opacity-50 ${VARIANT_CLS[a.variant ?? 'neutral']}`}
        >
          {a.label}
        </button>
      ))}
      <span className="ml-auto flex items-center gap-2">
        {trailing}
        <button
          onClick={onClear}
          className="rounded-md border border-slate-300 bg-white px-3 py-1
                     text-xs font-medium text-slate-700 hover:bg-slate-50"
        >
          Clear
        </button>
      </span>
    </div>
  );
}
