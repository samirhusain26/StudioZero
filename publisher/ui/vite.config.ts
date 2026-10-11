import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// The Pi backend (publisher/app/ui_server.py) serves the committed bundle (publisher/app/static) and /api on one origin.
// In dev, /api is proxied to a local backend started with --insecure-dev.
const api = process.env.SCALAR_UI_API ?? 'http://127.0.0.1:8765'

export default defineConfig({
  base: '/',
  plugins: [react()],
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: false,
    // No inline polyfill script: CSP is script-src 'self'.
    modulePreload: { polyfill: false },
    target: 'es2022',
  },
  server: {
    proxy: { '/api': { target: api, changeOrigin: false } },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['src/test/setup.ts'],
    restoreMocks: true,
  },
})
