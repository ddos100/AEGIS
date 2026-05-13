import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      // REST calls
      '/v1': { target: 'http://api:8000', changeOrigin: true },
      // WebSocket upgrades — required for the /v1/ws/discovery live feed.
      // Without ws:true the browser hits the Vite dev server, gets 404, and
      // the Shadow AI Radar never receives messages.
      '/v1/ws': { target: 'ws://api:8000', ws: true, changeOrigin: true },
    },
  },
});
