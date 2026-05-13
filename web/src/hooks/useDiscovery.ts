import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import type { DiscoveryFeedItem, DiscoveryVectorRow, TopSystem, WSMessage } from '@/types/discovery';

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
 * Subscribe to the live discovery WebSocket feed.
 *
 * Returns the most recent N messages, newest first. Auto-reconnects with
 * exponential backoff (1s → 30s) on close. Token is read from sessionStorage
 * to match the API client's auth flow.
 */
export function useDiscoveryStream(maxMessages = 50) {
  const [messages, setMessages] = useState<WSMessage[]>([]);
  const [connected, setConnected] = useState(false);
  const ref = useRef<WebSocket | null>(null);

  useEffect(() => {
    let backoff = 1000;
    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      const token = sessionStorage.getItem('aegis.token');
      if (!token) return;  // not authenticated yet — try again on next mount
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const host = (import.meta.env.VITE_API_URL || '/v1').replace(/^https?:\/\//, '');
      const url = `${proto}://${host.replace(/\/v1$/, '')}/v1/ws/discovery?token=${encodeURIComponent(token)}`;
      const ws = new WebSocket(url);
      ref.current = ws;

      ws.onopen = () => { setConnected(true); backoff = 1000; };
      ws.onclose = () => {
        setConnected(false);
        if (!cancelled) {
          reconnectTimer = setTimeout(connect, backoff);
          backoff = Math.min(backoff * 2, 30_000);
        }
      };
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data) as WSMessage;
          setMessages((prev) => [msg, ...prev].slice(0, maxMessages));
        } catch { /* malformed — ignore */ }
      };
    };

    connect();
    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ref.current?.close();
    };
  }, [maxMessages]);

  return { messages, connected };
}
