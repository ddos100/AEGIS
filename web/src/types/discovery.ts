// TS mirror of app/schemas/ingest.py + app/routes/discovery.py response shapes.

export interface DiscoveryFeedItem {
  occurred_at: string;
  catalogue_slug: string | null;
  ai_system_id: string | null;
  name: string | null;
  category: string | null;
  vector: string;
  source: string;
  user_email: string | null;
  department: string | null;
  is_shadow: boolean;
}

export interface TopSystem {
  id: string;
  name: string;
  category: string;
  is_shadow: boolean;
  event_count: number;
  unique_users: number;
}

export interface DiscoveryVectorRow {
  id: string;
  name: string;
  source: string;
  vector_type: string;
  status: string;
  last_sync_at: string | null;
  events_total: number;
  last_error: string | null;
}

export type WSMessage =
  | { type: 'new_system'; payload: {
        id: string; name: string; category: string; catalogue_slug: string;
        first_discovered_at: string; vector: string;
        detected_by_user?: string | null; department?: string | null;
      } }
  | { type: 'usage_spike'; payload: { ai_system_id: string; events: number } };
