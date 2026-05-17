export interface FrameworkBrief {
  id: string;
  slug: string;
  name: string;
  version: string;
  authority: string | null;
  jurisdiction: string | null;
  description: string | null;
  is_active: boolean;
}

export interface FrameworkScore {
  framework_id: string;
  slug: string;
  name: string;
  total_controls: number;
  by_status: Record<string, number>;
  score_pct: number;
  gaps: { control_id: string; title: string; category?: string | null; status: string }[];
}

export interface ReportBrief {
  id: string;
  report_type: string;
  framework_id: string | null;
  status: string;
  file_format: string;
  file_size_bytes: number | null;
  error: string | null;
  requested_at: string;
  completed_at: string | null;
}

export interface EcosystemNode {
  id: string;
  name: string;
  category: string;
  risk_level: string | null;
  is_shadow: boolean;
  usage_count: number;
  department: string | null;
}

export interface EcosystemEdge {
  source: string;
  target: string;
  kind: string;
}

export interface EcosystemGraph {
  nodes: EcosystemNode[];
  edges: EcosystemEdge[];
}

export interface DashboardOverview {
  // null while no system has been scored yet — the UI must distinguish
  // "0 by computation" (every system scored, all low) from "no data".
  risk_posture_score: number | null;
  scored_systems: number;
  total_systems: number;
  shadow_count: number;
  critical_count: number;
  high_count: number;
  aisia_pending_count: number;
  violations_open: number;
  framework_scores: FrameworkScore[];
  top_risks: { id: string; name: string; category: string; score: number;
               level: string; is_shadow: boolean }[];
  recent_discoveries: { occurred_at: string | null; catalogue_slug: string | null;
                        vector: string; name: string | null; is_shadow: boolean }[];
}
