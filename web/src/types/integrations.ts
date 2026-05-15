export interface IntegrationBrief {
  id: string;
  integration: string;
  kind: 'idp' | 'cloud' | 'saas';
  name: string;
  status: string;
  scopes: string[];
  last_used_at: string | null;
  last_sync_at: string | null;
  last_sync_result: Record<string, unknown>;
  last_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConnectorInfo {
  integration: string;
  kind: 'idp' | 'cloud' | 'saas';
  cls: string;
  doc: string;
}

export interface SyncRunResponse {
  ok: boolean;
  discovered_count: number;
  new_count: number;
  updated_count: number;
  error: string | null;
  extra: Record<string, unknown>;
}
