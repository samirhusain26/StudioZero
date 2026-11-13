import { expect, test } from '@playwright/test'

/**
 * Keyboard and focus (docs/PI_UI_REDESIGN_PLAN.md §9) against a backend with fixture state:
 *   SCALAR_UI_URL (default http://127.0.0.1:8765), SCALAR_UI_PASSCODE (required).
 */
const PASSCODE = process.env.SCALAR_UI_PASSCODE ?? ''

test.describe('Keyboard', () => {
  test.skip(!PASSCODE, 'Set SCALAR_UI_PASSCODE to run against a fixture backend.')

  test('focus lands on the title; tabs, chips and disclosures work from the keyboard', async ({ page }) => {
    await page.goto('/')
    await page.getByLabel('Passcode').fill(PASSCODE)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Studio' })).toBeVisible()

    // Studio, Review and Publish are the primary destinations. Utilities stay secondary.
    const nav = page.getByRole('navigation', { name: 'Sections' })
    await expect(nav.getByRole('link', { name: 'Studio', exact: true })).toBeVisible()
    const labels = await nav.locator('.nav-label').allTextContents()
    expect(labels).toEqual(['Studio', 'Review', 'Publish'])
    await nav.getByRole('link', { name: 'Review', exact: true }).focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('heading', { level: 1, name: 'Review' })).toBeFocused()
    // Tab from the title goes on into the screen's own content, in reading order.
    await page.keyboard.press('Tab')
    expect(await page.evaluate(() => Boolean(document.activeElement?.closest('main')))).toBe(true)

    // A chip toggles with Space and keeps focus (it does not move to the title).
    const approved = page.getByRole('group', { name: 'Show' }).getByRole('button', { name: 'Approved' })
    await approved.focus()
    await page.keyboard.press('Space')
    await expect(approved).toHaveAttribute('aria-pressed', 'true')
    await expect(approved).toBeFocused()

    // Operations remain available from the responsive More utility menu.
    const more = page.locator('details.utility-menu > summary')
    await more.focus()
    await page.keyboard.press('Enter')
    const operations = page.locator('.utility-menu').getByRole('link', { name: 'Operations' })
    await operations.focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('heading', { level: 1, name: 'Activity' })).toBeFocused()
    const menu = page.locator('details.menu > summary')
    await menu.focus()
    await page.keyboard.press('Enter')
    await expect(page.getByLabel('Platform')).toBeVisible()

    // The previous operations dashboard remains reachable through its old deep anchor.
    await page.goto('/#/home#platforms')
    await expect(page.getByRole('region', { name: 'Your loop' })).toBeVisible()
    const step = page.getByRole('region', { name: 'Your loop' }).getByRole('button').first()
    await step.focus()
    await page.keyboard.press('Enter')
    await expect(step).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByTestId('loop-fact')).not.toBeEmpty()
  })
})
