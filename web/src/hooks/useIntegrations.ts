import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { ConnectorInfo, IntegrationBrief, SyncRunResponse } from '@/types/integrations';

export function useIntegrations() {
  return useQuery({
    queryKey: ['integrations'],
    queryFn: async () => (await api.get<IntegrationBrief[]>('/integrations')).data,
    refetchInterval: 30_000,
  });
}

export function useConnectorTypes() {
  return useQuery({
    queryKey: ['integrations', 'types'],
    queryFn: async () => (await api.get<ConnectorInfo[]>('/integrations/types')).data,
    staleTime: 5 * 60_000,
  });
}

export function useCreateIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: {
      integration: string; name: string; credentials: Record<string, unknown>; scopes?: string[];
    }) => (await api.post<IntegrationBrief>('/integrations', payload)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['integrations'] }),
  });
}

export function useTestIntegration() {
  return useMutation({
    mutationFn: async (id: string) =>
      (await api.post<SyncRunResponse>(`/integrations/${id}/test`)).data,
  });
}

export function useSyncIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) =>
      (await api.post<SyncRunResponse>(`/integrations/${id}/sync`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['integrations'] }),
  });
}

export function useDeleteIntegration() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => { await api.delete(`/integrations/${id}`); },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['integrations'] }),
  });
}
