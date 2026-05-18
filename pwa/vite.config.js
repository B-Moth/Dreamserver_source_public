import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

const rawBase = process.env.PWA_BASE_PATH || '/app/'
const normalizedBase = rawBase.startsWith('/') ? rawBase : `/${rawBase}`
const pwaBase = normalizedBase.endsWith('/') ? normalizedBase : `${normalizedBase}/`

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      strategies: 'injectManifest',
      srcDir: 'src',
      filename: 'sw-push.js',
      manifest: {
        name: 'DreamCatcher',
        short_name: 'DreamCatcher',
        description: 'Journal de rêves personnel',
        theme_color: '#0e0e12',
        background_color: '#0e0e12',
        display: 'standalone',
        orientation: 'portrait',
        start_url: pwaBase,
        scope: pwaBase,
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png' }
        ]
      }
    })
  ],
  base: pwaBase,
  server: { allowedHosts: 'all' },
})
