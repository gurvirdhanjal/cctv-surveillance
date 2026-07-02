import { test as base, expect, type Page } from '@playwright/test'

// Credentials seeded by scripts/seed_admin_user.py + scripts/seed_demo_data.py
const CREDS = {
  admin:   { username: 'admin',   password: 'admin123' },
  guard:   { username: 'guard',   password: 'guard123' },
  manager: { username: 'manager', password: 'manager123' },
} as const

type Role = keyof typeof CREDS

async function loginAs(page: Page, role: Role): Promise<void> {
  await page.goto('/login')
  await page.getByLabel(/username/i).fill(CREDS[role].username)
  await page.getByLabel(/password/i).fill(CREDS[role].password)
  await page.getByRole('button', { name: /sign in/i }).click()
  // Wait for redirect away from /login
  await page.waitForURL((url) => !url.pathname.endsWith('/login'), { timeout: 10_000 })
}

type TestFixtures = {
  asGuard:   Page
  asAdmin:   Page
  asManager: Page
}

export const test = base.extend<TestFixtures>({
  asGuard: async ({ page }, use) => {
    await loginAs(page, 'guard')
    await use(page)
  },
  asAdmin: async ({ page }, use) => {
    await loginAs(page, 'admin')
    await use(page)
  },
  asManager: async ({ page }, use) => {
    await loginAs(page, 'manager')
    await use(page)
  },
})

export { expect }
