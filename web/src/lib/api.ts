import axios, { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { sessionStore } from '@/lib/session';

const baseURL = (import.meta.env.VITE_API_URL as string | undefined) || '/v1';

export const api = axios.create({ baseURL, timeout: 15_000 });

// ---------- request: attach rotating access token ----------
api.interceptors.request.use((config) => {
  const token = sessionStore.accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // Echo the rotating session id so server logs / audit_log can correlate
  // requests within a single (rotating) session without holding any
  // long-lived identifier on the client.
  const sid = sessionStore.sessionId;
  if (sid) config.headers['X-Aegis-Session'] = sid;
  return config;
});

// ---------- response: one transparent refresh on 401, then retry ----------
type RetriableConfig = InternalAxiosRequestConfig & { _aegisRetried?: boolean };

api.interceptors.response.use(
  (resp) => resp,
  async (err: AxiosError) => {
    const cfg = err.config as RetriableConfig | undefined;
    if (
      err.response?.status === 401 &&
      cfg &&
      !cfg._aegisRetried &&
      sessionStore.current &&
      !cfg.url?.startsWith('/auth/')
    ) {
      cfg._aegisRetried = true;
      try {
        await sessionStore.refresh();
        const token = sessionStore.accessToken;
        if (token) cfg.headers.Authorization = `Bearer ${token}`;
        return api.request(cfg);
      } catch {
        // Refresh failed — fall through; session was already cleared.
      }
    }
    return Promise.reject(err);
  },
);
