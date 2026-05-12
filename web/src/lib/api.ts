import axios from 'axios';

const baseURL = import.meta.env.VITE_API_URL || '/v1';

export const api = axios.create({ baseURL, timeout: 15_000 });

// Auth header injection — Phase 0 stub. Will be wired to Keycloak token in next pass.
api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('aegis.token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});
