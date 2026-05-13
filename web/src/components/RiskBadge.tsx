import type { RiskLevel } from '@/types/registry';

const CLASS_MAP: Record<RiskLevel, string> = {
  critical: 'badge-critical',
  high: 'badge-high',
  medium: 'badge-medium',
  low: 'badge-low',
};

export function RiskBadge({ level, score }: { level: RiskLevel | null; score: number | null }) {
  if (!level) return <span className="badge bg-slate-100 text-slate-500">Unscored</span>;
  return (
    <span className={CLASS_MAP[level]} title={score != null ? `Score: ${score}` : undefined}>
      {level.toUpperCase()}
      {score != null && <span className="ml-1 opacity-70">{score}</span>}
    </span>
  );
}

export function CompletenessBar({ value }: { value: number }) {
  const color =
    value >= 80 ? 'bg-green-500' :
    value >= 60 ? 'bg-yellow-500' :
    value >= 40 ? 'bg-orange-500' :
    'bg-red-500';
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-200">
        <div className={`h-full ${color}`} style={{ width: `${value}%` }} />
      </div>
      <span className="text-xs text-slate-600 tabular-nums">{value}%</span>
    </div>
  );
}
