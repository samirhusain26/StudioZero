import { defineConfig } from '@playwright/test'

// Smoke tests run against a running backend (publisher/app/ui_server.py serving publisher/app/static via its default --static, or dist/ via --static)
// with fixture state. Nothing here starts a server or touches real publishing state.
const baseURL = process.env.SCALAR_UI_URL ?? 'http://127.0.0.1:8765'
// Optional: SCALAR_UI_BROWSER_CHANNEL=chrome uses installed Google Chrome (decodes H.264)
// instead of Playwright's bundled Chromium.
const channel = process.env.SCALAR_UI_BROWSER_CHANNEL

export default defineConfig({
  testDir: 'e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [['list']],
  use: {
    baseURL,
    trace: 'retain-on-failure',
    timezoneId: 'UTC',
  },
  projects: [
    {
      name: 'mobile',
      use: {
        browserName: 'chromium',
        ...(channel ? { channel } : {}),
        viewport: { width: 375, height: 812 },
        isMobile: true,
        hasTouch: true,
        deviceScaleFactor: 2,
      },
    },
    {
      name: 'desktop',
      use: {
        browserName: 'chromium',
        ...(channel ? { channel } : {}),
        viewport: { width: 1440, height: 900 },
      },
    },
  ],
})
