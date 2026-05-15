import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type {
  DashboardOverview,
  EcosystemGraph,
  FrameworkBrief,
  FrameworkScore,
  ReportBrief,
} from '@/types/compliance';

export function useFrameworks() {
  return useQuery({
    queryKey: ['compliance', 'frameworks'],
    queryFn: async () => (await api.get<FrameworkBrief[]>('/compliance/frameworks')).data,
  });
}

export interface ControlBrief {
  id: string;
  framework_id: string;
  control_id: string;
  title: string;
  description: string | null;
  requirement_text: string | null;
  source_ref: string | null;
  category: string | null;
  is_mandatory: boolean;
  applies_to: string[];
  evidence_hints: string[];
}

export function useFrameworkControls(slug: string | undefined) {
  return useQuery({
    queryKey: ['compliance', 'frameworks', slug, 'controls'],
    enabled: !!slug,
    // The API returns controls already sorted by control_id; do not re-sort
    // here so what the user sees matches the deterministic digest 1:1.
    queryFn: async () =>
      (await api.get<ControlBrief[]>(`/compliance/frameworks/${slug}/controls`)).data,
  });
}

export interface MappingDetail {
  id: string;
  tenant_id: string;
  control_id: string;
  ai_system_id: string | null;
  status: 'implemented' | 'partial' | 'not_implemented' | 'not_applicable' | 'not_assessed';
  implementation_notes: string | null;
  evidence_refs: string[];
  last_assessed_at: string | null;
  next_review_date: string | null;
  created_at: string;
  updated_at: string;
}

/** All mappings for a framework, deterministically ordered (control_id, ai_system_id). */
export function useFrameworkMappings(slug: string | undefined) {
  return useQuery({
    queryKey: ['compliance', 'frameworks', slug, 'mappings'],
    enabled: !!slug,
    queryFn: async () =>
      (await api.get<MappingDetail[]>(`/compliance/frameworks/${slug}/mappings`)).data,
  });
}

export function useFrameworkScore(slug: string | undefined) {
  return useQuery({
    queryKey: ['compliance', 'frameworks', slug, 'score'],
    enabled: !!slug,
    queryFn: async () =>
      (await api.get<FrameworkScore>(`/compliance/frameworks/${slug}/score`)).data,
  });
}

export function useAutoAssess() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (slug: string) =>
      (await api.post(`/compliance/frameworks/${slug}/auto-assess`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['compliance'] }),
  });
}

export function useReports() {
  return useQuery({
    queryKey: ['reports'],
    queryFn: async () => (await api.get<ReportBrief[]>('/reports')).data,
    refetchInterval: 15_000,
  });
}

export function useGenerateReport() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: { report_type: string; framework_id?: string; file_format?: string }) =>
      (await api.post<ReportBrief>('/reports/generate', payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reports'] }),
  });
}

export function useDashboardOverview() {
  return useQuery({
    queryKey: ['dashboard', 'overview'],
    queryFn: async () => (await api.get<DashboardOverview>('/dashboard/overview')).data,
    refetchInterval: 60_000,
  });
}

export function useEcosystemMap() {
  return useQuery({
    queryKey: ['dashboard', 'ecosystem-map'],
    queryFn: async () => (await api.get<EcosystemGraph>('/dashboard/ecosystem-map')).data,
    refetchInterval: 60_000,
  });
}
