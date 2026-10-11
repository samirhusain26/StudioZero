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
    await expect(page.getByRole('heading', { level: 1, name: 'Home' })).toBeVisible()

    // The five sections are links in visual order, each reachable with Tab.
    const nav = page.getByRole('navigation', { name: 'Sections' })
    const labels = await nav.getByRole('link').allTextContents()
    expect(labels.map((l) => l.replace(/^\W+/, ''))).toEqual(['Home', 'Library', 'Schedule', 'Activity', 'Settings'])
    await nav.getByRole('link', { name: 'Library', exact: true }).focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('heading', { level: 1, name: 'Library' })).toBeFocused()
    // Tab from the title goes on into the screen's own content, in reading order.
    await page.keyboard.press('Tab')
    expect(await page.evaluate(() => Boolean(document.activeElement?.closest('main')))).toBe(true)

    // A chip toggles with Space and keeps focus (it does not move to the title).
    const approved = page.getByRole('group', { name: 'Show' }).getByRole('button', { name: 'Approved' })
    await approved.focus()
    await page.keyboard.press('Space')
    await expect(approved).toHaveAttribute('aria-pressed', 'true')
    await expect(approved).toBeFocused()

    // Activity: the ⋯ menu is a disclosure that opens with Enter.
    await nav.getByRole('link', { name: 'Activity', exact: true }).focus()
    await page.keyboard.press('Enter')
    await expect(page.getByRole('heading', { level: 1, name: 'Activity' })).toBeFocused()
    const menu = page.locator('details.menu > summary')
    await menu.focus()
    await page.keyboard.press('Enter')
    await expect(page.getByLabel('Platform')).toBeVisible()

    // Home: a loop step opens its fact with the keyboard.
    await nav.getByRole('link', { name: 'Home', exact: true }).focus()
    await page.keyboard.press('Enter')
    const step = page.getByRole('region', { name: 'Your loop' }).getByRole('button').first()
    await step.focus()
    await page.keyboard.press('Enter')
    await expect(step).toHaveAttribute('aria-expanded', 'true')
    await expect(page.getByTestId('loop-fact')).not.toBeEmpty()
  })
})
