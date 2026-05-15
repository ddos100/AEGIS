export type RiskLevel = 'critical' | 'high' | 'medium' | 'low';

export interface RiskAssessmentRow {
  ai_system_id: string;
  data_sensitivity_score: number;
  ai_capability_score: number;
  regulatory_exposure_score: number;
  access_scope_score: number;
  provider_trust_score: number;
  total_score: number;
  risk_level: RiskLevel;
  scoring_inputs: Record<string, unknown>;
  ai_narrative: string | null;
  ai_model_used: string | null;
  calculated_by: string;
  calculated_at: string;
}

export interface RiskSummary {
  total_systems: number;
  by_level: Record<string, number>;
  avg_score: number;
  top_drivers: { name: string; avg: number }[];
}

export interface AISIADetail {
  id: string;
  ai_system_id: string;
  status: 'initiated' | 'in_progress' | 'completed' | 'approved' | 'rejected';
  impact_level: string | null;
  intended_purpose_confirmed: string | null;
  affected_population: string | null;
  severity_assessment: string | null;
  reversibility_assessment: string | null;
  human_oversight_assessment: string | null;
  treatment_decision: string | null;
  societal_impact_notes: string | null;
  initiated_at: string;
  completed_at: string | null;
  approved_at: string | null;
  due_date: string | null;
  ai_draft: string | null;
  review_notes: string | null;
}

export interface PolicyDetail {
  id: string;
  name: string;
  description: string | null;
  is_active: boolean;
  priority: number;
  conditions: Record<string, unknown>;
  action: 'allow' | 'monitor' | 'alert' | 'block' | 'require_approval';
  action_config: Record<string, unknown>;
  template_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface PolicyTemplateBrief {
  id: string;
  name: string;
  description: string;
  rule_count: number;
}

export interface ViolationRow {
  id: string;
  policy_id: string;
  ai_system_id: string | null;
  user_id: string | null;
  vector: string | null;
  action_taken: string;
  violation_context: Record<string, unknown>;
  resolved: boolean;
  resolution_notes: string | null;
  occurred_at: string;
}
