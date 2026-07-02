import { defineConfig, devices } from '@playwright/test'

/**
 * E2E test configuration.
 *
 * Requires the full stack running before test:e2e:
 *   docker compose -f e2e/docker-compose.yml up -d   (DB + Redis)
 *   uvicorn vms.api.main:socket_app --port 8080       (FastAPI + SPA)
 *
 * For automated CI use the e2e/run.sh script which seeds and starts everything.
 * Playwright connects to http://localhost:8080 (FastAPI serves frontend/dist/).
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,           // sequential: tests share a single DB state
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,                     // single worker: avoid race conditions on shared DB
  reporter: [
    ['html', { open: 'never' }],
    ['line'],
  ],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8080',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'on-first-retry',
    actionTimeout: 10_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
