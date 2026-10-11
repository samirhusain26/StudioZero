import { expect, test } from '@playwright/test'

/**
 * Guide at phone width (375×812, the "mobile" project) against a backend with fixture state:
 *   SCALAR_UI_URL (default http://127.0.0.1:8765), SCALAR_UI_PASSCODE (required).
 */
const PASSCODE = process.env.SCALAR_UI_PASSCODE ?? ''

test.describe('Guide', () => {
  test.skip(!PASSCODE, 'Set SCALAR_UI_PASSCODE to run against a fixture backend.')

  test('renders at 375 px without horizontal overflow, and deep links scroll to a heading', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'mobile', 'Phone-width check only.')
    await page.goto('/')
    await page.getByLabel('Passcode').fill(PASSCODE)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Home' })).toBeVisible()

    // The guide is the header help icon (it opens the current screen's section), not a tab.
    await expect(page.getByRole('navigation', { name: 'Sections' }).getByRole('link', { name: 'Guide' })).toHaveCount(0)
    await page.getByRole('link', { name: /^Help/ }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Guide' })).toBeVisible()
    await expect(page).toHaveURL(/#\/guide\/how-it-works$/)
    await expect(page.getByTestId('guide-meta')).toHaveText(/^Guide updated \d{4}-\d{2}-\d{2} · running /)
    await expect(page.getByRole('navigation', { name: 'Contents' })).toBeVisible()

    const overflow = await page.evaluate(() => {
      const root = document.scrollingElement ?? document.documentElement
      return { scrollWidth: root.scrollWidth, innerWidth: window.innerWidth }
    })
    expect(overflow.innerWidth).toBe(375)
    expect(overflow.scrollWidth, 'Guide: horizontal scroll at 375 px').toBeLessThanOrEqual(overflow.innerWidth)

    await page.goto('/#/guide/update-the-pi')
    const heading = page.locator('#guide-update-the-pi')
    await expect(heading).toBeVisible()
    await expect(heading).toBeInViewport()
    const after = await page.evaluate(() => (document.scrollingElement ?? document.documentElement).scrollWidth <= window.innerWidth)
    expect(after).toBe(true)
  })
})
