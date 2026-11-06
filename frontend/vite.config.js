// Vite config: React, Tailwind, and dev proxies to Claimwise API (:8000) and Mock Services (:8100).
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '^/connector-api/api/connectors(?:/|$)': {
        target: process.env.CLAIMWISE_CONNECTOR_DEV_URL ?? 'http://127.0.0.1:8101',
        rewrite: (path) => path.replace(/^\/connector-api/, ''),
      },
      '/mock-api': {
        target: 'http://localhost:8100',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/mock-api/, ''),
      },
    },
  },
})
