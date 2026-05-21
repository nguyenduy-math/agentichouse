import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Frontend gọi /api/* ; backend (FastAPI) gắn router ở gốc (/chat, /health, /ingest).
// Vì vậy ta strip tiền tố /api khi proxy sang backend.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ''),
      },
    },
  },
})
