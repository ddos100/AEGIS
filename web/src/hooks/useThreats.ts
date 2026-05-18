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

// ---------------------------------------------------------------------------
// Exposures (Phase 7.1)
// ---------------------------------------------------------------------------

export type ExposureStatus = 'exposed' | 'not_exposed' | 'unknown' | 'mitigated';

export interface ExposureBrief {
  id: string;
  tenant_id: string;
  threat_id: string;
  status: ExposureStatus;
  last_evaluated_at: string;
  threat_external_id: string;
  threat_title: string;
  threat_severity: ThreatBrief['severity'];
  threat_classes: string[];
  threat_vectors: string[];
}

export interface ExposureDetail extends ExposureBrief {
  reasons: string[];
  evidence_refs: string[];
  missing_telemetry: string[];
  threat_source_ref: string;
  threat_verbatim_description: string;
  threat_exposure_check: Record<string, unknown>;
  threat_mitigation: { preferred?: unknown[]; alternates?: unknown[] } | null;
}

export interface ExposureListResponse {
  items: ExposureBrief[];
  by_status: Record<ExposureStatus, number>;
  total: number;
}

export function useExposures(opts: { status?: string[]; severity?: string[] } = {}) {
  return useQuery({
    queryKey: ['exposures', opts],
    queryFn: async () => {
      const params = new URLSearchParams();
      opts.status?.forEach(s => params.append('status', s));
      opts.severity?.forEach(s => params.append('severity', s));
      const qs = params.toString();
      return (await api.get<ExposureListResponse>(`/exposures${qs ? '?' + qs : ''}`)).data;
    },
    placeholderData: (prev) => prev,
  });
}

export function useExposure(threatExternalId: string | undefined) {
  return useQuery({
    queryKey: ['exposures', threatExternalId],
    enabled: !!threatExternalId,
    queryFn: async () =>
      (await api.get<ExposureDetail>(`/exposures/${threatExternalId}`)).data,
  });
}

export async function recomputeExposures(): Promise<{
  tenant_id: string;
  threats_total: number;
  exposed: number;
  not_exposed: number;
  unknown: number;
  skipped_by_sector: number;
  mitigations?: { exposures_seen: number; created: number; refreshed: number; skipped_terminal: number };
}> {
  return (await api.post('/exposures/recompute')).data;
}

// ---------------------------------------------------------------------------
// Mitigations (Phase 7.4 — propose-only)
// ---------------------------------------------------------------------------

export type MitigationStatus =
  | 'proposed' | 'queued' | 'rejected' | 'dismissed'
  | 'applied'  | 'verified' | 'drifted' | 'rolled_back' | 'failed';

export interface MitigationBrief {
  id: string;
  tenant_id: string;
  threat_id: string;
  exposure_id: string | null;
  integration: string;
  action: string;
  preference: 'preferred' | 'alternate';
  requires_module: string | null;
  severity_min: string | null;
  status: MitigationStatus;
  status_reason: string | null;
  proposed_at: string;
  approved_at: string | null;
  applied_at: string | null;
  verified_at: string | null;
  rolled_back_at: string | null;
  threat_external_id: string;
  threat_title: string;
  threat_severity: ThreatBrief['severity'];
}

export interface MitigationDetail extends MitigationBrief {
  params: Record<string, unknown>;
  idempotency_key: string;
  last_error: string | null;
  threat_source_ref: string;
}

export interface MitigationListResponse {
  items: MitigationBrief[];
  by_status: Record<MitigationStatus, number>;
  total: number;
}

export function useMitigations(opts: {
  status?: MitigationStatus[];
  severity?: string[];
  integration?: string[];
} = {}) {
  return useQuery({
    queryKey: ['mitigations', opts],
    queryFn: async () => {
      const params = new URLSearchParams();
      opts.status?.forEach(s => params.append('status', s));
      opts.severity?.forEach(s => params.append('severity', s));
      opts.integration?.forEach(s => params.append('integration', s));
      const qs = params.toString();
      return (await api.get<MitigationListResponse>(`/mitigations${qs ? '?' + qs : ''}`)).data;
    },
    placeholderData: (prev) => prev,
  });
}

export async function decideMitigation(
  id: string,
  decision: 'approve' | 'reject' | 'dismiss',
  reason?: string,
): Promise<MitigationDetail> {
  return (await api.post(`/mitigations/${id}/${decision}`, { reason })).data;
}

// Phase 7.5 — push / verify / rollback ----------------------------------

export interface PushReceipt {
  ok: boolean;
  dry_run: boolean;
  vendor_ref: string | null;
  detail: string;
  error: string | null;
  mitigation: MitigationDetail;
}

export interface VerifyReceipt {
  verified: boolean;
  drifted: boolean;
  missing: boolean;
  dry_run: boolean;
  detail: string;
  error: string | null;
  mitigation: MitigationDetail;
}

export async function pushMitigation(id: string): Promise<PushReceipt> {
  return (await api.post(`/mitigations/${id}/push`)).data;
}

export async function verifyMitigation(id: string): Promise<VerifyReceipt> {
  return (await api.post(`/mitigations/${id}/verify`)).data;
}

export async function rollbackMitigation(id: string, reason?: string): Promise<PushReceipt> {
  return (await api.post(`/mitigations/${id}/rollback`, { reason })).data;
}

// ---------------------------------------------------------------------------
// Threat-Feed review queue (Phase 7.2)
// ---------------------------------------------------------------------------

export type DraftReviewStatus = 'pending_review' | 'published' | 'rejected' | 'superseded';

export interface DraftBrief {
  id: string;
  source: string;
  upstream_id: string;
  review_status: DraftReviewStatus;
  ingested_at: string;
  reviewed_at: string | null;
  threat_id: string;
  title: string;
  severity: ThreatBrief['severity'];
  classes: string[];
  vectors: string[];
}

export interface DraftDetail extends DraftBrief {
  draft: Record<string, unknown>;
  review_notes: string | null;
  source_fingerprint: string;
  published_threat_id: string | null;
}

export interface DraftListResponse {
  items: DraftBrief[];
  by_status: Record<string, number>;
  total: number;
}

export interface FeedSourceInfo {
  source: string;
  class: string;
  default_jurisdictions: string[];
}

export interface IngestRunResult {
  source: string;
  ok: boolean;
  seen: number;
  drafted: number;
  duplicates: number;
  skipped: number;
  errored: number;
  error: string | null;
}

export function usePendingDrafts() {
  return useQuery({
    queryKey: ['threat-feed', 'pending'],
    queryFn: async () => (await api.get<DraftListResponse>('/threats/feed/pending-review')).data,
    staleTime: 30_000,
  });
}

export function useDraft(id: string | undefined) {
  return useQuery({
    queryKey: ['threat-feed', 'draft', id],
    enabled: !!id,
    queryFn: async () => (await api.get<DraftDetail>(`/threats/feed/drafts/${id}`)).data,
  });
}

export function useFeedSources() {
  return useQuery({
    queryKey: ['threat-feed', 'sources'],
    queryFn: async () => (await api.get<FeedSourceInfo[]>('/threats/feed/sources')).data,
    staleTime: 5 * 60_000,
  });
}

export async function refreshFeeds(): Promise<IngestRunResult[]> {
  return (await api.post('/threats/feed/refresh')).data;
}

export async function publishDraft(
  id: string,
  body: { edited_draft?: Record<string, unknown>; notes?: string; write_yaml?: boolean } = {},
): Promise<DraftDetail> {
  return (await api.post(`/threats/feed/drafts/${id}/publish`, body)).data;
}

export async function rejectDraft(id: string, notes?: string): Promise<DraftDetail> {
  return (await api.post(`/threats/feed/drafts/${id}/reject`, { notes })).data;
}

// ---------------------------------------------------------------------------
// AEGIS Endpoint Agent (Phase 7.6)
// ---------------------------------------------------------------------------

export interface EndpointDevice {
  id: string;
  hostname: string;
  os: 'linux' | 'darwin' | 'windows';
  arch: string;
  agent_version: string;
  last_heartbeat_at: string | null;
  enrolled_at: string;
  revoked_at: string | null;
}

export interface EndpointAgentEventOut {
  id: string;
  device_id: string;
  kind: string;
  occurred_at: string;
  ingested_at: string;
  payload: Record<string, unknown>;
  hostname: string | null;
}

export interface DeviceListResponse {
  items: EndpointDevice[];
  total: number;
  healthy: number;
}

export interface EAEventListResponse {
  items: EndpointAgentEventOut[];
  by_kind: Record<string, number>;
  total: number;
}

export interface EnrollmentCode {
  enrollment_code: string;
  expires_at: string;
  ingest_url: string;
}

export function useDevices() {
  return useQuery({
    queryKey: ['ea', 'devices'],
    queryFn: async () => (await api.get<DeviceListResponse>('/endpoint-agent/devices')).data,
    refetchInterval: 30_000,
  });
}

export function useEAEvents(opts: { kind?: string; device_id?: string; limit?: number } = {}) {
  return useQuery({
    queryKey: ['ea', 'events', opts],
    queryFn: async () => {
      const p = new URLSearchParams();
      if (opts.kind) p.set('kind', opts.kind);
      if (opts.device_id) p.set('device_id', opts.device_id);
      if (opts.limit) p.set('limit', String(opts.limit));
      const qs = p.toString();
      return (await api.get<EAEventListResponse>(`/endpoint-agent/events${qs ? '?' + qs : ''}`)).data;
    },
    refetchInterval: 30_000,
  });
}

export async function mintEnrollmentCode(): Promise<EnrollmentCode> {
  return (await api.post('/endpoint-agent/enrollment-code')).data;
}

export async function revokeDevice(id: string): Promise<EndpointDevice> {
  return (await api.post(`/endpoint-agent/devices/${id}/revoke`)).data;
}
