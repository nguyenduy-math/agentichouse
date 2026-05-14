import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server on :5173. The /api prefix is proxied to the FastAPI backend so the
// browser makes same-origin calls in development (no CORS dance needed).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
