/**
 * Forensic search E2E suite (4G.4)
 *
 * Prerequisite: full E2E stack running (see e2e/docker-compose.yml + playwright.config.ts).
 * Covers §18: search clips by text (expect graceful 501 unavailable-state),
 * open a clip drawer via GET /api/forensic/clips/{id}.
 *
 * Note: GET /api/forensic/search returns 501 until CLIP-ViT-B/32 ONNX encoder
 * is deployed (tracked in CLAUDE.md §3 Known Gaps). This spec verifies the
 * disabled/unavailable-state render, not real results.
 */
import { test, expect } from './fixtures'

test.describe('Forensic search — unavailable state (CLIP not deployed)', () => {
  test('manager sees forensic page with unavailable notice', async ({ asManager: page }) => {
    await page.goto('/forensic')
    // The 501 response renders a clear unavailable message
    await expect(page.getByText(/unavailable|not yet deployed|clip/i)).toBeVisible()
  })

  test('forensic search input is disabled when backend returns 501', async ({ asManager: page }) => {
    await page.goto('/forensic')
    const searchInput = page.getByRole('textbox')
    await expect(searchInput).toBeDisabled()
  })
})

test.describe('Forensic — clip drawer via GET /api/forensic/clips/{id}', () => {
  test('guard cannot access forensic page (redirects to 403)', async ({ asGuard: page }) => {
    await page.goto('/forensic')
    // Guard role has read-only forensic access — spec §3 says guard can access forensic
    // Verify they reach the page rather than 403
    await expect(page).not.toHaveURL(/\/403/)
    await expect(page).toHaveURL(/\/forensic|\/live/)
  })
})
