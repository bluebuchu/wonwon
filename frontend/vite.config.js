import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      workbox: {
        runtimeCaching: [
          {
            urlPattern: /\/api\/issues\/latest$/,
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-issues',
              expiration: { maxEntries: 1, maxAgeSeconds: 60 * 60 * 24 },
              networkTimeoutSeconds: 5,
            },
          },
        ],
      },
      manifest: {
        name: '탐구 이슈 엔진',
        short_name: '탐구엔진',
        description: '매주 업데이트되는 고등학생 계열별 탐구 주제',
        lang: 'ko',
        theme_color: '#6366f1',
        background_color: '#0f0f1a',
        display: 'standalone',
        start_url: '/',
        icons: [
          { src: '/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icon-512-maskable.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      '/api': 'http://localhost:8001',
    },
  },
})
