import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type {
  AISIADetail,
  PolicyDetail,
  PolicyTemplateBrief,
  RiskAssessmentRow,
  RiskSummary,
  ViolationRow,
} from '@/types/risk';

// ---- Risk ----

export function useRiskSummary() {
  return useQuery({
    queryKey: ['risk', 'summary'],
    queryFn: async () => (await api.get<RiskSummary>('/risk/summary')).data,
    refetchInterval: 60_000,
  });
}

export function useSystemRiskHistory(systemId: string | undefined) {
  return useQuery({
    queryKey: ['risk', 'systems', systemId],
    enabled: !!systemId,
    queryFn: async () =>
      (await api.get<RiskAssessmentRow[]>(`/risk/systems/${systemId}/assessment`)).data,
  });
}

export function useReassess() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (systemId: string) =>
      (await api.post<RiskAssessmentRow>(`/risk/systems/${systemId}/assess`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['risk'] });
      qc.invalidateQueries({ queryKey: ['registry'] });
    },
  });
}

// ---- AISIA ----

export function useAISIAList(status?: string[]) {
  return useQuery({
    queryKey: ['aisia', 'list', status],
    queryFn: async () =>
      (await api.get<AISIADetail[]>('/aisia', { params: { status } })).data,
  });
}

export function useAISIA(id: string | undefined) {
  return useQuery({
    queryKey: ['aisia', id],
    enabled: !!id,
    queryFn: async () => (await api.get<AISIADetail>(`/aisia/${id}`)).data,
  });
}

export function useInitiateAISIA() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (systemId: string) =>
      (await api.post<AISIADetail>(`/aisia/systems/${systemId}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['aisia'] }),
  });
}

export function useUpdateAISIA(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Partial<AISIADetail>) =>
      (await api.patch<AISIADetail>(`/aisia/${id}`, payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['aisia'] }),
  });
}

export function useSubmitAISIA(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => (await api.post<AISIADetail>(`/aisia/${id}/submit`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['aisia'] }),
  });
}

export function useAISIADraft() {
  return useMutation({
    mutationFn: async (id: string) =>
      (await api.get<{ draft: string | null; cached: boolean; fallback?: string }>(`/aisia/${id}/draft`)).data,
  });
}

// ---- Policies ----

export function usePolicies() {
  return useQuery({
    queryKey: ['policies'],
    queryFn: async () => (await api.get<PolicyDetail[]>('/policies')).data,
  });
}

export function usePolicyTemplates() {
  return useQuery({
    queryKey: ['policies', 'templates'],
    queryFn: async () =>
      (await api.get<PolicyTemplateBrief[]>('/policies/templates')).data,
  });
}

export function useImportTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (templateId: string) =>
      (await api.post<PolicyDetail[]>(`/policies/templates/${templateId}/import`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['policies'] }),
  });
}

export function useUpdatePolicy(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Partial<PolicyDetail>) =>
      (await api.patch<PolicyDetail>(`/policies/${id}`, payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['policies'] }),
  });
}

export function useDeletePolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => { await api.delete(`/policies/${id}`); },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['policies'] }),
  });
}

// ---- Violations ----

export function useViolations(resolved?: boolean) {
  return useQuery({
    queryKey: ['violations', resolved],
    queryFn: async () =>
      (await api.get<ViolationRow[]>('/violations', { params: { resolved } })).data,
  });
}

export function useResolveViolation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, notes }: { id: string; notes?: string }) =>
      (await api.patch<ViolationRow>(`/violations/${id}/resolve`, { notes })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['violations'] }),
  });
}
