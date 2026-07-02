/**
 * Admin view E2E suite (4G.3)
 *
 * Prerequisite: full E2E stack running (see e2e/docker-compose.yml + playwright.config.ts).
 * Covers §18: enrol person, calibrate camera, edit zone, create maintenance window.
 */
import { test, expect } from './fixtures'

test.describe('Admin — persons', () => {
  test('admin can open enrolment wizard', async ({ asAdmin: page }) => {
    await page.goto('/admin/persons')
    await page.getByRole('button', { name: /enrol/i }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
  })

  test('enrolment wizard validates employee ID format', async ({ asAdmin: page }) => {
    await page.goto('/admin/persons')
    await page.getByRole('button', { name: /enrol/i }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByLabel(/employee id/i).fill('INVALID')
    await dialog.getByRole('button', { name: /next/i }).click()
    // Validation error should appear
    await expect(dialog.getByRole('alert')).toBeVisible()
  })
})

test.describe('Admin — cameras', () => {
  test('camera list shows seeded cameras', async ({ asAdmin: page }) => {
    await page.goto('/admin/cameras')
    await expect(page.getByText('Main Entrance')).toBeVisible()
    await expect(page.getByText('Assembly Line A')).toBeVisible()
  })

  test('camera detail page has five tabs', async ({ asAdmin: page }) => {
    await page.goto('/admin/cameras')
    await page.getByText('Main Entrance').click()
    await expect(page.getByRole('tab', { name: /overview/i })).toBeVisible()
    await expect(page.getByRole('tab', { name: /hardware/i })).toBeVisible()
    await expect(page.getByRole('tab', { name: /overrides/i })).toBeVisible()
    await expect(page.getByRole('tab', { name: /maintenance/i })).toBeVisible()
    await expect(page.getByRole('tab', { name: /calibration/i })).toBeVisible()
  })
})

test.describe('Admin — zones', () => {
  test('zone editor shows seeded zones', async ({ asAdmin: page }) => {
    await page.goto('/admin/zones')
    await expect(page.getByText('Reception')).toBeVisible()
    await expect(page.getByText('Assembly Floor')).toBeVisible()
  })
})

test.describe('Admin — maintenance', () => {
  test('admin can open create-window modal', async ({ asAdmin: page }) => {
    await page.goto('/admin/maintenance')
    await page.getByRole('button', { name: /create|add/i }).click()
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.keyboard.press('Escape')
  })
})
