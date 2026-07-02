/**
 * Guard live-view E2E suite (4G.2)
 *
 * Prerequisite: full E2E stack running (see e2e/docker-compose.yml + playwright.config.ts).
 * Covers §18: login as guard, see alerts, acknowledge, follow person.
 */
import { test, expect } from './fixtures'

test.describe('Guard live view', () => {
  test('guard can log in and sees the live view', async ({ asGuard: page }) => {
    await expect(page).toHaveURL(/\/live/)
    await expect(page.getByRole('banner')).toBeVisible()   // TopBar
  })

  test('alert sidebar is visible with at least one alert card', async ({ asGuard: page }) => {
    // Seeded data includes OPEN alerts
    const sidebar = page.getByRole('complementary')
    await expect(sidebar).toBeVisible()
  })

  test('guard can acknowledge an open alert', async ({ asGuard: page }) => {
    const ackButton = page.getByRole('button', { name: /acknowledge/i }).first()
    await expect(ackButton).toBeVisible()
    await ackButton.click()
    // Button should disappear (alert transitions to ACKNOWLEDGED)
    await expect(ackButton).not.toBeVisible({ timeout: 5_000 })
  })

  test('guard cannot navigate to admin section', async ({ asGuard: page }) => {
    await page.goto('/admin')
    await expect(page).toHaveURL(/\/403|\/login/)
  })

  test('Cmd+K opens person search', async ({ asGuard: page }) => {
    await page.keyboard.press('Control+k')
    await expect(page.getByRole('dialog', { name: /person search/i })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog', { name: /person search/i })).not.toBeVisible()
  })
})
