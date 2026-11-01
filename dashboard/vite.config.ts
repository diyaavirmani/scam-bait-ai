import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Build into app/web/dist; FastAPI serves it on the same origin as the API (no hard-coded URLs).
export default defineConfig({
  plugins: [react()],
  base: '/',
  build: { outDir: '../app/web/dist', emptyOutDir: true, chunkSizeWarningLimit: 1200 },
  esbuild: { charset: 'ascii' },
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8000', '/health': 'http://127.0.0.1:8000' },
  },
})
