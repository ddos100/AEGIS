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
