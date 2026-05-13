import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type {
  AISystemDetail,
  AISystemListItem,
  AIServiceBrief,
  Page,
  RegistryStats,
} from '@/types/registry';

export interface ListSystemsParams {
  page?: number;
  per_page?: number;
  q?: string;
  category?: string[];
  risk_level?: string[];
  status?: string[];
  is_shadow?: boolean;
  sort?: string;
}

export function useSystems(params: ListSystemsParams = {}) {
  return useQuery({
    queryKey: ['registry', 'systems', params],
    queryFn: async () => {
      const { data } = await api.get<Page<AISystemListItem>>('/registry/systems', { params });
      return data;
    },
  });
}

export function useSystem(id: string | undefined) {
  return useQuery({
    queryKey: ['registry', 'systems', id],
    enabled: !!id,
    queryFn: async () => {
      const { data } = await api.get<AISystemDetail>(`/registry/systems/${id}`);
      return data;
    },
  });
}

export function useRegistryStats() {
  return useQuery({
    queryKey: ['registry', 'stats'],
    queryFn: async () => (await api.get<RegistryStats>('/registry/stats')).data,
  });
}

export function useCreateSystem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Partial<AISystemDetail>) =>
      (await api.post<AISystemDetail>('/registry/systems', payload)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['registry'] });
    },
  });
}

export function useUpdateSystem(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (payload: Partial<AISystemDetail>) =>
      (await api.patch<AISystemDetail>(`/registry/systems/${id}`, payload)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['registry'] });
    },
  });
}

export function useArchiveSystem() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/registry/systems/${id}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['registry'] }),
  });
}

// ---- Catalogue ----

export function useCatalogueServices(params: { q?: string; category?: string; page?: number; per_page?: number } = {}) {
  return useQuery({
    queryKey: ['catalogue', 'services', params],
    queryFn: async () =>
      (await api.get<Page<AIServiceBrief>>('/catalogue/services', { params })).data,
  });
}

export function useCatalogueCategories() {
  return useQuery({
    queryKey: ['catalogue', 'categories'],
    queryFn: async () => (await api.get<{ category: string; count: number }[]>('/catalogue/categories')).data,
  });
}

export function useAddFromCatalogue() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { catalogue_service_id: string; intended_purpose?: string }) =>
      (await api.post<AISystemDetail>('/registry/systems/from-catalogue', body)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['registry'] }),
  });
}
