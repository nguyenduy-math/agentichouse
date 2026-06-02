import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        // Use 127.0.0.1 (not localhost): on Windows "localhost" can resolve to
        // IPv6 ::1 first, but uvicorn binds IPv4 127.0.0.1 by default, so the
        // proxy connection is refused. 127.0.0.1 forces a matching IPv4 target.
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      }
    }
  }
})
