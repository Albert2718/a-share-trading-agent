import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    headers: {
      'Cache-Control': 'no-store',
    },
    proxy: {
      '/api': {
        target: process.env.DOCKER_ENV ? 'http://api:8000' : 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
