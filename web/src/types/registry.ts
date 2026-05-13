// Shared TS types mirroring the Pydantic registry/catalogue schemas.
// Update both sides together if a field changes.

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

export type RiskLevel = 'critical' | 'high' | 'medium' | 'low';
export type SystemStatus = 'active' | 'pilot' | 'decommissioned' | 'under_review';
export type AISIAStatus = 'not_started' | 'in_progress' | 'completed' | 'requires_review';
export type PolicyStatus = 'allow' | 'monitor' | 'alert' | 'block' | 'requires_approval';
export type DeploymentType =
  | 'cloud_saas'
  | 'cloud_api'
  | 'on_premise'
  | 'browser_extension'
  | 'desktop_agent'
  | 'embedded_saas';

export interface AISystemListItem {
  id: string;
  name: string;
  provider_slug: string | null;
  category: string;
  subcategory: string | null;
  deployment_type: DeploymentType;
  status: SystemStatus;
  risk_level: RiskLevel | null;
  current_risk_score: number | null;
  policy_status: PolicyStatus;
  completeness_score: number;
  is_shadow: boolean;
  aisia_status: AISIAStatus;
  discovery_sources: string[];
  department_id: string | null;
  owner_user_id: string | null;
  last_seen_at: string | null;
  created_at: string;
}

export interface AISystemDetail extends AISystemListItem {
  tenant_id: string;
  internal_alias: string | null;
  version: string | null;
  catalogue_service_id: string | null;
  provider_id: string | null;
  provider_name_freetext: string | null;
  intended_purpose: string | null;
  actual_use_observed: string | null;
  user_population: string | null;
  affected_data_subjects: string[];
  data_types_processed: string[];
  output_type: string | null;
  human_oversight_desc: string | null;
  geographic_scope: string[];
  business_unit: string | null;
  first_deployed_at: string | null;
  decommission_date: string | null;
  aisia_impact_level: string | null;
  eu_ai_act_category: string | null;
  compliance_flags: Record<string, unknown>;
  notes: string | null;
  tags: string[];
  custom_fields: Record<string, unknown>;
  first_discovered_at: string | null;
  last_risk_assessed_at: string | null;
  created_by: string | null;
  updated_by: string | null;
}

export interface AIServiceBrief {
  id: string;
  catalogue_id: string;
  name: string;
  provider_slug: string | null;
  category: string;
  subcategory: string | null;
  description: string | null;
  eu_ai_act_cat: string | null;
  tags: string[];
}

export interface RegistryStats {
  total: number;
  shadow_count: number;
  completeness_avg: number;
  by_risk_level: Record<string, number>;
  by_category: Record<string, number>;
  by_status: Record<string, number>;
  aisia_pending_count: number;
}
