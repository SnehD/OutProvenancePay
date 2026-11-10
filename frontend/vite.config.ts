import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The browser talks to the backend directly (CORS is configured server-side via OPP_CORS_ORIGINS).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true },
});
