import { useEffect, useRef, useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { sessionStore } from '@/lib/session';
import type { DiscoveryFeedItem, DiscoveryVectorRow, TopSystem, WSMessage } from '@/types/discovery';

export function useTestBroadcast() {
  return useMutation({
    mutationFn: async () =>
      (await api.post<{ published: boolean; channel: string }>('/discovery/test-broadcast')).data,
  });
}

export function useDiscoveryFeed(sinceHours = 24, limit = 50) {
  return useQuery({
    queryKey: ['discovery', 'feed', sinceHours, limit],
    queryFn: async () =>
      (await api.get<DiscoveryFeedItem[]>('/discovery/feed', {
        params: { since_hours: sinceHours, limit },
      })).data,
    refetchInterval: 30_000,
  });
}

export function useTopSystems(sinceHours = 168, limit = 10) {
  return useQuery({
    queryKey: ['usage', 'top-systems', sinceHours, limit],
    queryFn: async () =>
      (await api.get<TopSystem[]>('/usage/top-systems', {
        params: { since_hours: sinceHours, limit },
      })).data,
  });
}

export function useDiscoveryVectors() {
  return useQuery({
    queryKey: ['discovery', 'vectors'],
    queryFn: async () => (await api.get<DiscoveryVectorRow[]>('/discovery/vectors')).data,
  });
}

/**
 * Build the WebSocket URL for the discovery feed.
 *
 * Three forms of VITE_API_URL must work:
 *   1. unset / "/v1"            → connect to same-origin /v1/ws/... (Vite dev proxy)
 *   2. "http://localhost:8000/v1" → ws://localhost:8000/v1/ws/...
 *   3. "https://aegis.example.com/v1" → wss://aegis.example.com/v1/ws/...
 */
export function buildWsUrl(token: string): string {
  const raw = (import.meta.env.VITE_API_URL || '/v1') as string;
  let origin: string;
  if (raw.startsWith('http://') || raw.startsWith('https://')) {
    const u = new URL(raw);
    const proto = u.protocol === 'https:' ? 'wss:' : 'ws:';
    origin = `${proto}//${u.host}`;
  } else {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    origin = `${proto}//${location.host}`;
  }
  return `${origin}/v1/ws/discovery?token=${encodeURIComponent(token)}`;
}

/**
 * Subscribe to the live discovery WebSocket feed.
 *
 * Returns the most recent N messages, newest first. Auto-reconnects with
 * exponential backoff (1s → 30s) on close.
 *
 * Token sourcing: reads from the v1.0 session store (rotating access
 * token in `localStorage.aegis.session.v1`). When the session rotates
 * silently (every ~10 minutes by sessionStore.refresh()), this hook
 * tears down the current socket and reconnects with the fresh token,
 * so the live feed survives token rotation without operator action.
 */
export function useDiscoveryStream(maxMessages = 50) {
  const [messages, setMessages] = useState<WSMessage[]>([]);
  const [connected, setConnected] = useState(false);
  const ref = useRef<WebSocket | null>(null);

  useEffect(() => {
    let backoff = 1000;
    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let currentToken: string | null = null;

    const connect = () => {
      const token = sessionStore.accessToken;
      if (!token) {
        // No session yet (login screen still showing) — keep retrying
        // so the feed snaps online the moment login lands.
        reconnectTimer = setTimeout(connect, 5_000);
        return;
      }
      currentToken = token;
      const url = buildWsUrl(token);
      try {
        const ws = new WebSocket(url);
        ref.current = ws;
        ws.onopen    = () => { setConnected(true); backoff = 1000; };
        ws.onclose   = () => {
          setConnected(false);
          if (!cancelled) {
            reconnectTimer = setTimeout(connect, backoff);
            backoff = Math.min(backoff * 2, 30_000);
          }
        };
        ws.onerror   = (e) => console.warn('[AEGIS] WS error', e);
        ws.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data) as WSMessage;
            setMessages((prev) => [msg, ...prev].slice(0, maxMessages));
          } catch { /* malformed — ignore */ }
        };
      } catch (err) {
        console.warn('[AEGIS] WS connect failed', err);
        reconnectTimer = setTimeout(connect, backoff);
        backoff = Math.min(backoff * 2, 30_000);
      }
    };

    // Subscribe to session changes so a silent token rotation (every
    // ~10 minutes) tears down the old socket and reconnects with the
    // fresh access token. Without this, the live feed would die when
    // the access token expired and reconnect attempts would all 401.
    const unsubscribe = sessionStore.subscribe((s) => {
      const next = s?.access_token ?? null;
      if (next !== currentToken) {
        // Drop the existing socket; the onclose handler triggers
        // connect() which picks up the new token.
        ref.current?.close();
      }
    });

    connect();
    return () => {
      cancelled = true;
      unsubscribe();
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ref.current?.close();
    };
  }, [maxMessages]);

  return { messages, connected };
}
