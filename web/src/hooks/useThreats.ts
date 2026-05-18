import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';

export interface ThreatBrief {
  id: string;
  threat_id: string;
  title: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  classes: string[];
  vectors: string[];
  source_ref: string;
  mitre_atlas_ids: string[];
  owasp_llm_ids: string[];
  sector_amplifiers: string[];
  applies_to_jurisdictions: string[];
  catalogue_version: string;
  last_updated: string;
}

export interface ThreatDetail extends ThreatBrief {
  verbatim_description: string;
  description: string | null;
  exposure_check: Record<string, unknown>;
  mitigation: { preferred?: unknown[]; alternates?: unknown[]; rollback?: unknown[] } | null;
  evidence_hints: string[];
  compliance_implications: string[];
  created_at: string;
  updated_at: string;
}

export interface ThreatListResponse {
  items: ThreatBrief[];
  total: number;
  page: number;
  pages: number;
  per_page: number;
}

export interface ThreatQuery {
  q?: string;
  severity?: string[];
  vector?: string;
  class?: string;
  sector?: string;
  page?: number;
  per_page?: number;
}

export function useThreats(query: ThreatQuery) {
  return useQuery({
    queryKey: ['threats', query],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (query.q) params.set('q', query.q);
      if (query.severity) query.severity.forEach(s => params.append('severity', s));
      if (query.vector) params.set('vector', query.vector);
      if (query.class) params.set('class', query.class);
      if (query.sector) params.set('sector', query.sector);
      params.set('page', String(query.page ?? 1));
      params.set('per_page', String(query.per_page ?? 50));
      return (await api.get<ThreatListResponse>(`/threats?${params.toString()}`)).data;
    },
    placeholderData: (prev) => prev,
  });
}

export function useThreat(threatId: string | undefined) {
  return useQuery({
    queryKey: ['threats', threatId],
    enabled: !!threatId,
    queryFn: async () =>
      (await api.get<ThreatDetail>(`/threats/${threatId}`)).data,
  });
}

export interface ModuleEntitlement {
  module_sku: string;
  edition: string | null;
  valid_to: string | null;
  feature_flags: Record<string, unknown>;
  limits: Record<string, unknown>;
}

export function useLicence() {
  return useQuery({
    queryKey: ['licence'],
    queryFn: async () => (await api.get<ModuleEntitlement[]>(`/licence`)).data,
    staleTime: 60_000,
  });
}
