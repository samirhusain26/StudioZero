import { expect, test } from '@playwright/test'

/**
 * A first-time owner uses the redesigned Studio → legacy batch workflow → Review → Publish journey.
 * It writes to the fixture state (an upload and content approvals), so it only runs when asked:
 *   SCALAR_UI_PASSCODE, SCALAR_UI_JOURNEY_BATCH = a finalized throwaway batch folder (fixture work/2026-10-second).
 * The fixture may have locally eligible draft channels while all channels remain disabled for publishing. This test may
 * generate a local draft; it never enables a channel, approves a schedule, resumes publishing or invokes activation.
 */
const PASSCODE = process.env.SCALAR_UI_PASSCODE ?? ''
const BATCH = process.env.SCALAR_UI_JOURNEY_BATCH ?? ''

test.describe('First-time owner journey', () => {
  test.skip(!PASSCODE || !BATCH, 'Set SCALAR_UI_PASSCODE and SCALAR_UI_JOURNEY_BATCH (fixture state only).')

  test('create and review fixture work without enabling publishing', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'mobile', 'Phone only (it changes fixture state).')
    await page.goto('/')
    await page.getByLabel('Passcode').fill(PASSCODE)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Studio' })).toBeVisible()
    await page.goto('/#/home#platforms')
    const loop = page.getByRole('region', { name: 'Your loop' })
    await expect(loop.getByTestId('next-step')).toContainText(/^Step [1-6] · /)

    // Make: open the unique Scalargame project and its existing batch workflow.
    await page.getByRole('navigation', { name: 'Sections' }).getByRole('link', { name: 'Studio', exact: true }).click()
    await expect(page.locator('.project-card')).toHaveCount(4)
    await page.locator('.project-card').filter({ has: page.getByRole('heading', { name: 'Scalargame' }) }).getByRole('link', { name: 'Open' }).click()
    await page.getByRole('link', { name: 'Legacy batch workflow' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Make a batch' })).toBeVisible()
    await expect(page.getByRole('heading', { level: 2, name: /Let Claude make it.*on the Mac/ })).toBeVisible()
    for (const name of [/Checkpoint 0/, /Checkpoint 1/, /Checkpoint 3/, /Finalize/]) await page.getByRole('checkbox', { name }).check()

    // Upload: step 4 takes the finalized folder.
    await page.getByLabel('Batch folder').setInputFiles(BATCH)
    await expect(page.getByText(/finalized\./)).toBeVisible()
    await page.getByRole('button', { name: 'Upload batch' }).click()
    await expect(page.getByText(/All files verified\./)).toBeVisible({ timeout: 60_000 })
    await page.getByRole('button', { name: /review in the library/ }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Review' })).toBeVisible()
    // Scope the repeatable review pass to this batch; importing the same finalized folder is idempotent.
    await page.goto('/#/library?project=scalargame&batch=2026-10-second')
    await expect(page.getByRole('heading', { level: 1, name: 'Review' })).toBeVisible()

    // Review: tap the first card, then Approve and Next through the list until Done.
    await page.getByTestId('episode-card').first().click()
    const bar = page.getByRole('group', { name: 'Review actions' })
    for (let i = 0; i < 20; i++) {
      await expect(bar).toBeVisible()
      // Wait for this episode's library entry (its status) before deciding.
      await expect(page.getByTestId('episode-question')).toContainText(/Ready for review|Approved|Withdrawn|Invalid|Awaiting files/)
      const approve = bar.getByRole('button', { name: 'Approve' })
      if (await approve.isEnabled()) {
        await approve.click()
        await page.getByRole('dialog', { name: /^Approve 1 video/ }).getByRole('button', { name: 'Approve' }).click()
        await expect(page.getByText(/^Approved 1 of 1\./)).toBeVisible()
      }
      const next = bar.getByRole('link', { name: 'Next →' })
      if (!(await next.isVisible())) break
      const target = decodeURIComponent((await next.getAttribute('href'))?.split('/')[3] ?? '')
      await next.click()
      // The new episode is on screen (its id is in the facts line), not the previous one mid-navigation.
      await expect(page.getByTestId('episode-question')).toContainText(target)
    }
    await bar.getByRole('link', { name: 'Done: back to the Library' }).click()
    await expect(page.getByText(/^Nothing to review/)).toBeVisible()

    // Generate a local draft from eligible fixture routes. Channels remain disabled; do not approve the schedule.
    await page.getByRole('navigation', { name: 'Sections' }).getByRole('link', { name: 'Publish', exact: true }).click()
    const draft = page.getByTestId('new-draft')
    await expect(draft.getByTestId('preset-times')).toContainText('Instagram 18:00')
    const channels = await page.evaluate(async () => {
      const response = await fetch('/api/schedule', { credentials: 'same-origin' })
      return (await response.json()).channels as Array<{ enabled: boolean }>
    })
    expect(channels.length).toBeGreaterThan(0)
    expect(channels.every((channel) => !channel.enabled)).toBe(true)
    await expect(draft.getByLabel('Start date')).toHaveValue(/^\d{4}-\d{2}-\d{2}$/)
    await draft.getByRole('button', { name: 'Generate draft' }).click()
    const preview = page.getByTestId('draft-preview')
    await expect(preview).toBeVisible({ timeout: 30_000 })
    await expect(preview.getByTestId('draft-summary')).toContainText(/\d+ of \d+ requested slots? fillable/)
    await expect(preview.getByTestId('job-time').first()).toBeVisible()
    await expect(preview.getByRole('article').first().getByText('Exact caption')).toBeVisible()
    const approval = page.getByTestId('approval-panel')
    await expect(approval.getByRole('button', { name: 'Approve schedule' })).toBeVisible()
    await expect(approval.getByText(/Ready to approve\.|channel|blocked|not verified/i)).toBeVisible()

    // Settings remain reachable; no activation or resume action is performed.
    await page.locator('details.utility-menu > summary').click()
    await page.locator('.utility-menu').getByRole('link', { name: 'Settings' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Settings' })).toBeVisible()
    await expect(page.getByRole('button', { name: /resume|unpause/i })).toHaveCount(0)
  })
})
