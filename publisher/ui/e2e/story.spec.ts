import { expect, test } from '@playwright/test'

/**
 * Studio › Story jobs in the real UI against a live story worker (engines/story/src/agent.py) behind a local studio
 * proxy (publisher/app/studio_proxy.py --dev-worker): SCALAR_UI_PASSCODE, SCALAR_UI_STORY=1. Read-only on the worker
 * except opening an estimate (nothing is run: keep STUDIO_AGENT_ALLOW_PAID unset). SCALAR_UI_STORY_SERIES = a series job
 * with finished steps (default: the first series listed). SCALAR_UI_STORY_SHOTS = a folder for screenshots.
 */
const PASSCODE = process.env.SCALAR_UI_PASSCODE ?? ''
const SHOTS = process.env.SCALAR_UI_STORY_SHOTS ?? ''

test.describe('Story jobs (live worker)', () => {
  test.skip(!PASSCODE || process.env.SCALAR_UI_STORY !== '1', 'Set SCALAR_UI_PASSCODE and SCALAR_UI_STORY=1 with a local worker and proxy.')

  test('worker status, jobs, a series with its files, an estimate, renders and settings', async ({ page }, testInfo) => {
    const shot = async (name: string) => {
      if (SHOTS) await page.screenshot({ path: `${SHOTS}/${testInfo.project.name}-${name}.png`, fullPage: true })
    }
    await page.goto('/')
    await page.getByLabel('Passcode').fill(PASSCODE)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await page.getByRole('navigation', { name: 'Sections' }).getByRole('link', { name: 'Studio', exact: true }).click()
    await page.getByRole('link', { name: 'Story jobs →' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Story jobs' })).toBeVisible()
    await expect(page.getByTestId('story-worker')).toContainText('Version')
    await expect(page.getByTestId('story-job').first()).toBeVisible()
    await shot('jobs')

    const series = process.env.SCALAR_UI_STORY_SERIES
    const row = series ? page.getByTestId('story-job').filter({ hasText: series }) : page.getByTestId('story-job').filter({ hasText: 'Animation series' }).first()
    await row.getByRole('link', { name: 'Open' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Story job' })).toBeVisible()
    await expect(page.getByTestId('story-step').filter({ hasText: 'Set designer' }).first()).toBeVisible()
    // Casting has character sheets and reference images; otherwise the first finished step.
    const casting = page.getByTestId('story-step').getByRole('button', { name: 'Casting' })
    await ((await casting.count()) > 0 ? casting : page.getByTestId('story-step').getByRole('button').first()).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.locator('li').first()).toBeVisible()
    // Media come from the laptop through the Pi (session cookie, same origin): images must decode.
    const images = dialog.locator('img')
    if ((await images.count()) > 0) {
      await expect.poll(() => images.first().evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true)
    }
    await shot('artifacts')
    await page.keyboard.press('Escape')
    await shot('job')

    await page.goto('/#/studio/jobs')
    await expect(page.getByTestId('story-job').first()).toBeVisible()
    const runnable = page.getByTestId('story-job').filter({ hasText: /Paused|Not started|Stopped with an error/ }).first()
    if ((await runnable.count()) > 0) {
      await runnable.getByRole('link', { name: 'Open' }).click()
      await page.getByRole('button', { name: /^(Start|Continue|Retry)…$/ }).click()
      const estimate = page.getByTestId('story-estimate')
      await expect(estimate).toContainText('Estimated:')
      await shot('estimate')
      await estimate.getByRole('button', { name: 'Cancel' }).click()
    }

    await page.goto('/#/studio/renders')
    await expect(page.getByRole('heading', { level: 1, name: 'Story renders' })).toBeVisible()
    await shot('renders')
    await page.goto('/#/studio/story-settings')
    await expect(page.getByRole('heading', { name: 'Keys' })).toBeVisible()
    await expect(page.getByTestId('story-model').first()).toBeVisible()
    await shot('settings')
  })
})
