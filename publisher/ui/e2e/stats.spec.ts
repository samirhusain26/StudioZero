import { expect, test } from '@playwright/test'

/**
 * Post stats controls against a fixture backend (publisher/tests/ui_fixture_state.py). Writes only the fixture's
 * STATE/metrics/ (the enabled flag and a request.json). No scalar-social-metrics.path runs locally, so a read
 * request stays pending: the panel must say it is waiting.
 */
const PASSCODE = process.env.SCALAR_UI_PASSCODE ?? ''

test.describe('Post stats controls', () => {
  test.skip(!PASSCODE, 'Set SCALAR_UI_PASSCODE to run against a fixture backend.')

  test('switch, read now (pending), funnel and System state', async ({ page }) => {
    await page.goto('/')
    await page.getByLabel('Passcode').fill(PASSCODE)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Home' })).toBeVisible()

    await page.goto('/#/studio/make')
    await expect(page.getByRole('heading', { level: 1, name: 'Make a batch' })).toBeVisible()
    await page.getByText('How the posts did', { exact: true }).click()
    const panel = page.getByTestId('post-stats')
    await expect(panel.getByRole('heading', { name: 'Post stats' })).toBeVisible()

    // The switch is a plain toggle button; flip it and back.
    const toggle = panel.getByRole('button', { name: 'Hourly reads', exact: true })
    const before = await toggle.getAttribute('aria-pressed')
    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-pressed', before === 'true' ? 'false' : 'true')
    await toggle.click()
    await expect(toggle).toHaveAttribute('aria-pressed', before ?? 'false')

    // Read now: nothing picks the request up locally, so it stays pending (an earlier project's request may still be waiting).
    const read = panel.getByRole('button', { name: 'Read stats now' })
    if ((await read.getAttribute('aria-disabled')) !== 'true') {
      await panel.getByText('Also read past days', { exact: true }).click()
      await panel.getByLabel('Also read past days (0–93)').fill('3')
      await read.click()
    }
    await expect(panel.getByText('Waiting for the Pi…')).toBeVisible()
    await expect(read).toHaveAttribute('aria-disabled', 'true')   // aria-disabled, so focus is kept
    await expect(panel.getByText(/scalar-social-metrics\.path is not active/)).toBeVisible()
    await expect(page.locator('.btn-primary')).toHaveCount(1)

    // Funnel: a real table (or its empty state) with the follows note.
    const funnel = page.getByTestId('funnel')
    await expect(funnel.getByText(/account-level for that day, not attributed to the video/)).toBeVisible()
    await expect(funnel.getByText(/X and TikTok come from Buffer/)).toBeVisible()
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    expect(overflow, 'no horizontal page scroll').toBeLessThanOrEqual(0)

    // Settings › System shows the state.
    await page.goto('/#/settings#system')
    const system = page.getByTestId('post-stats-system')
    await expect(system.locator('summary')).toHaveText(/^Post stats: hourly reads (on|off)$/)
    await system.locator('summary').click()
    await expect(system.getByText('Waiting', { exact: true })).toBeVisible()
  })
})
