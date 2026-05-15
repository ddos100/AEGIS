/**
 * AEGIS session manager.
 *
 * Persists Keycloak tokens in localStorage so the user stays logged in across
 * page reloads, and silently rotates them every ~10 minutes through the
 * backend `/v1/auth/refresh` proxy. The rotating `session_id` returned by the
 * server changes on every refresh, but the refresh chain keeps the user
 * authenticated indefinitely — there is no static credential held by the SPA.
 *
 * The store also exposes a tiny pub/sub so React components can re-render
 * when the session changes.
 */
import axios from 'axios';

const STORAGE_KEY = 'aegis.session.v1';
const ROTATION_LEAD_SECONDS = 300;       // refresh 5 min before expiry
const ROTATION_FLOOR_SECONDS = 60;       // never less than 1 min between rotations

const baseURL = (import.meta.env.VITE_API_URL as string | undefined) || '/v1';

export interface Session {
  access_token: string;
  refresh_token: string;
  expires_in: number;            // seconds at issue time
  refresh_expires_in: number;    // seconds at issue time
  session_id: string;            // rotating opaque id (sha256(sub|jti), 32 chars)
  issued_at: number;             // epoch ms (set client-side)
}

type Listener = (s: Session | null) => void;

class SessionStore {
  private session: Session | null = null;
  private listeners = new Set<Listener>();
  private rotationTimer: number | null = null;

  constructor() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as Session;
        if (this.isLive(parsed)) {
          this.session = parsed;
          this.scheduleRotation();
        } else {
          localStorage.removeItem(STORAGE_KEY);
        }
      }
    } catch {
      localStorage.removeItem(STORAGE_KEY);
    }
  }

  // ---------- public API ----------

  get current(): Session | null {
    return this.session;
  }

  get accessToken(): string | null {
    return this.session?.access_token ?? null;
  }

  get sessionId(): string | null {
    return this.session?.session_id ?? null;
  }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    fn(this.session);
    return () => { this.listeners.delete(fn); };
  }

  async login(username: string, password: string): Promise<Session> {
    const { data } = await axios.post(`${baseURL}/auth/login`, { username, password }, {
      timeout: 10_000,
    });
    const next: Session = { ...data, issued_at: Date.now() };
    this.set(next);
    return next;
  }

  async refresh(): Promise<Session | null> {
    if (!this.session) return null;
    try {
      const { data } = await axios.post(
        `${baseURL}/auth/refresh`,
        { refresh_token: this.session.refresh_token },
        { timeout: 10_000 },
      );
      const next: Session = { ...data, issued_at: Date.now() };
      this.set(next);
      return next;
    } catch (err) {
      // Refresh token rejected — the only path that forces re-login.
      this.clear();
      throw err;
    }
  }

  async logout(): Promise<void> {
    const rt = this.session?.refresh_token;
    this.clear();
    if (rt) {
      try {
        await axios.post(`${baseURL}/auth/logout`, { refresh_token: rt }, { timeout: 5_000 });
      } catch {
        // Best-effort; local state already cleared.
      }
    }
  }

  // ---------- internals ----------

  private set(s: Session): void {
    this.session = s;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
    this.emit();
    this.scheduleRotation();
  }

  private clear(): void {
    this.session = null;
    localStorage.removeItem(STORAGE_KEY);
    if (this.rotationTimer) {
      window.clearTimeout(this.rotationTimer);
      this.rotationTimer = null;
    }
    this.emit();
  }

  private emit(): void {
    for (const fn of this.listeners) fn(this.session);
  }

  /** Is the access token still valid (with a tiny clock-skew buffer)? */
  private isLive(s: Session): boolean {
    const expiresAt = s.issued_at + (s.refresh_expires_in * 1000);
    return expiresAt > Date.now() + 5_000;
  }

  /** Schedule the next silent rotation 5 minutes before the access token expires. */
  private scheduleRotation(): void {
    if (this.rotationTimer) {
      window.clearTimeout(this.rotationTimer);
      this.rotationTimer = null;
    }
    if (!this.session) return;
    const lifetimeMs = this.session.expires_in * 1000;
    const leadMs = ROTATION_LEAD_SECONDS * 1000;
    const floorMs = ROTATION_FLOOR_SECONDS * 1000;
    const delay = Math.max(floorMs, lifetimeMs - leadMs);
    this.rotationTimer = window.setTimeout(() => {
      this.refresh().catch(() => {
        // Swallowed — clear() already happened inside refresh().
      });
    }, delay);
  }
}

export const sessionStore = new SessionStore();

// ---------- React hook ----------
import { useEffect, useState } from 'react';

export function useSession(): Session | null {
  const [s, setS] = useState<Session | null>(sessionStore.current);
  useEffect(() => sessionStore.subscribe(setS), []);
  return s;
}
