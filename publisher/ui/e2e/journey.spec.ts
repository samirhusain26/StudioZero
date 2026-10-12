import { expect, test } from '@playwright/test'

/**
 * A first-time owner goes round the loop using only the screens (docs/PI_UI_REDESIGN_PLAN.md §9):
 * Home → Make a batch → (Mac) → Upload → Review → Schedule → typed approval → Settings › Activation command.
 * It writes to the fixture state (an upload and content approvals), so it only runs when asked:
 *   SCALAR_UI_PASSCODE, SCALAR_UI_JOURNEY_BATCH = a finalized throwaway batch folder (fixture work/2026-10-second),
 *   SCALAR_UI_ALLOW_APPROVE=1 also submits the schedule approval (never against real state).
 */
const PASSCODE = process.env.SCALAR_UI_PASSCODE ?? ''
const BATCH = process.env.SCALAR_UI_JOURNEY_BATCH ?? ''

test.describe('First-time owner journey', () => {
  test.skip(!PASSCODE || !BATCH, 'Set SCALAR_UI_PASSCODE and SCALAR_UI_JOURNEY_BATCH (fixture state only).')

  test('round the loop from Home without the guide', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'mobile', 'Phone only (it changes fixture state).')
    await page.goto('/')
    await page.getByLabel('Passcode').fill(PASSCODE)
    await page.getByRole('button', { name: 'Sign in' }).click()
    const loop = page.getByRole('region', { name: 'Your loop' })
    await expect(loop.getByTestId('next-step')).toContainText(/^Step [1-6] · /)

    // Make: the Mac step is shown as numbered steps; the prompt and the checklist live here.
    await page.getByRole('navigation', { name: 'Sections' }).getByRole('link', { name: 'Studio', exact: true }).click()
    await page.getByRole('link', { name: 'Make a Scalargame batch →' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Make a batch' })).toBeVisible()
    await expect(page.getByRole('heading', { level: 2, name: /Let Claude make it.*on the Mac/ })).toBeVisible()
    for (const name of [/Checkpoint 0/, /Checkpoint 1/, /Checkpoint 3/, /Finalize/]) await page.getByRole('checkbox', { name }).check()

    // Upload: step 4 takes the finalized folder.
    await page.getByLabel('Batch folder').setInputFiles(BATCH)
    await expect(page.getByText(/finalized\./)).toBeVisible()
    await page.getByRole('button', { name: 'Upload batch' }).click()
    await expect(page.getByText(/All files verified\./)).toBeVisible({ timeout: 60_000 })
    await page.getByRole('button', { name: /review in the library/ }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Library' })).toBeVisible()

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

    // Schedule: Home now points at the next step; the preset plan generates a draft.
    await page.getByRole('navigation', { name: 'Sections' }).getByRole('link', { name: 'Schedule', exact: true }).click()
    await page.getByTestId('new-draft').getByRole('button', { name: 'Generate draft' }).click()
    await expect(page.getByTestId('draft-preview')).toBeVisible({ timeout: 30_000 })
    await page.getByRole('button', { name: 'Go to approval ↓' }).click()
    const panel = page.getByTestId('approval-panel')
    // One tap approves (no typed phrase since 2026-10-09).
    await expect(panel.getByText('Ready to approve.')).toBeVisible()
    await expect(panel.getByRole('button', { name: 'Approve schedule' })).toBeEnabled()
    if (process.env.SCALAR_UI_ALLOW_APPROVE === '1') await panel.getByRole('button', { name: 'Approve schedule' }).click()

    // Post: the owner's activation command, from Settings.
    await page.goto('/#/settings#activation')
    await expect(page.getByRole('heading', { level: 2, name: 'Activation' })).toBeVisible()
    await expect(page.getByText('First activation (owner, sudo; done once on 2026-10-09)')).toBeVisible()
    await expect(page.getByRole('button', { name: /resume|unpause/i })).toHaveCount(0)
  })
})
