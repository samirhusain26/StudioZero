import { expect, test, type Page } from '@playwright/test'

/**
 * Mobile smoke test (375×812) against a backend with fixture state:
 *   SCALAR_UI_URL       (default http://127.0.0.1:8765)
 *   SCALAR_UI_PASSCODE  (required)
 * This smoke suite never approves a schedule or enables channels. Draft generation is local fixture state only.
 */
const PASSCODE = process.env.SCALAR_UI_PASSCODE ?? ''
async function checkLayout(page: Page, where: string) {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(overflow, `${where}: horizontal scroll at 375 px`).toBeLessThanOrEqual(0)
  const small = await page.evaluate(() =>
    [...document.querySelectorAll('button')]
      .filter((b) => {
        const r = b.getBoundingClientRect()
        const style = getComputedStyle(b)
        return r.width > 0 && r.height > 0 && style.visibility !== 'hidden'
      })
      .map((b) => ({ text: (b.textContent ?? '').trim().slice(0, 40), height: b.getBoundingClientRect().height }))
      .filter((b) => b.height < 43.5),
  )
  expect(small, `${where}: buttons shorter than 44 px`).toEqual([])
}

async function openUtility(page: Page, label: string) {
  const sidebarLink = page.locator('.nav-utilities').getByRole('link', { name: label, exact: true })
  if (await sidebarLink.isVisible()) return sidebarLink.click()
  const menu = page.locator('details.utility-menu')
  if (!(await menu.evaluate((element: HTMLDetailsElement) => element.open))) await menu.locator('summary').click()
  await page.locator(`details.utility-menu a[href="${label === 'Settings' ? '#/settings' : label === 'Operations' ? '#/activity' : '#/guide'}"]`).click()
}

/** Jump with the three primary destinations and verify their visible page titles. */
async function open(page: Page, label: string) {
  const link = page.getByRole('navigation', { name: 'Sections' }).getByRole('link', { name: label, exact: true })
  await link.click()
  await expect(link).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('heading', { level: 1, name: label })).toBeVisible()
}

test.describe('Scalar publishing UI smoke', () => {
  test.skip(!PASSCODE, 'Set SCALAR_UI_PASSCODE to run the smoke test against a fixture backend.')

  test('sign in → Studio → project tools → Review → Publish → Operations', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText(/Backend reachable/)).toBeVisible()
    await checkLayout(page, 'passcode')
    await page.getByLabel('Passcode').fill(PASSCODE)
    await page.getByRole('button', { name: 'Sign in' }).click()

    // Home is the four-project Studio. The historic operations dashboard and its anchor remain available.
    await expect(page.getByRole('heading', { level: 1, name: 'Studio' })).toBeVisible()
    await expect(page.locator('.project-card')).toHaveCount(4)
    await expect(page.locator('.nav-list').getByRole('link')).toHaveCount(3)
    await page.goto('/#/home#platforms')
    const loop = page.getByRole('region', { name: 'Your loop' })
    await expect(loop.getByRole('button', { name: /^Step \d, / })).toHaveCount(6)
    await expect(loop.getByTestId('next-step')).toContainText(/^Step [1-6] · /)
    const platforms = page.getByRole('region', { name: 'Platforms' })
    await expect(platforms.getByTestId('platform-row')).toHaveCount(7)
    await expect(platforms.getByTestId('platform-row').first().getByRole('img')).toHaveCount(3)
    await checkLayout(page, 'operations dashboard deep link')
    await page.getByRole('navigation', { name: 'Sections' }).getByRole('link', { name: 'Studio', exact: true }).click()

    // Every project appears once; Scalargame retains browser export and its existing batch path.
    await expect(page.locator('.project-card')).toHaveCount(4)
    await checkLayout(page, 'studio')
    await page.locator('.project-card').filter({ has: page.getByRole('heading', { name: 'Scalargame' }) }).getByRole('link', { name: 'Open' }).click()
    await expect(page.getByRole('heading', { level: 2, name: 'Scalargame' })).toBeVisible()
    await page.getByRole('link', { name: 'Legacy batch workflow' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Make a batch' })).toBeVisible()
    await expect(page.getByTestId('prompt-builder')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Copy prompt for Claude' })).toBeEnabled()
    await checkLayout(page, 'make')
    await page.getByRole('group', { name: 'Project' }).getByRole('link', { name: 'Originals' }).click()
    await expect(page.getByText(/Upload the finalized batch folder in Library › Add batch/)).toBeVisible()
    await checkLayout(page, 'make originals')

    // Review retains the finalized importer and playable episode review.
    await open(page, 'Review')
    await expect(page.getByRole('group', { name: 'Show' }).getByRole('button', { name: /^To review/ })).toHaveAttribute('aria-pressed', 'true')
    await page.getByRole('group', { name: 'Show' }).getByRole('button', { name: 'All' }).click()
    await checkLayout(page, 'library')
    const card = page.getByTestId('episode-card').first()
    await expect(card).toBeVisible()
    await card.click()
    await expect(page.getByRole('heading', { level: 1, name: 'Episode' })).toBeVisible()
    await expect(page.getByTestId('step-line')).toHaveText(/^Step 3 of 6 · Review/)
    const bar = page.getByRole('group', { name: 'Review actions' })
    await expect(bar.getByRole('button', { name: 'Feedback' })).toBeVisible()
    const video = page.locator('video.review-player')
    await expect(video).toHaveAttribute('src', /\/api\/media\/videos\/[0-9a-f]{64}\.mp4\?t=/)
    await expect(video).toHaveAttribute('controls', '')
    const src = (await video.getAttribute('src')) ?? ''
    const media = await page.request.get(src, { headers: { Range: 'bytes=0-1023' } })
    expect([200, 206]).toContain(media.status())
    expect(media.headers()['content-type']).toContain('video/mp4')
    const canPlayH264 = await video.evaluate((v: HTMLVideoElement) => v.canPlayType('video/mp4; codecs="avc1.42E01E"') !== '')
    if (canPlayH264) {
      // Branded Chrome can decode H.264; open-source Chromium cannot, so only the byte check runs there.
      await expect.poll(() => video.evaluate((v: HTMLVideoElement) => v.readyState), { timeout: 15_000 }).toBeGreaterThanOrEqual(1)
    }
    await checkLayout(page, 'episode review')

    // Make a batch: the Mac step shown as numbered steps with a local checklist.
    await page.goto('/#/next-batch')
    await expect(page).toHaveURL(/#\/studio\/make$/)
    await expect(page.getByRole('heading', { level: 1, name: 'Make a batch' })).toBeVisible()
    await expect(page.getByTestId('make-checklist').getByRole('checkbox')).toHaveCount(5)
    await checkLayout(page, 'make a batch')

    // Publish is explicit about unavailable channels; fixture channels remain disabled.
    await open(page, 'Publish')
    const newDraft = page.getByTestId('new-draft')
    await expect(newDraft.getByTestId('generator-form')).toHaveCount(0)
    await expect(newDraft.getByTestId('preset-times')).toContainText('Instagram 18:00')
    const scheduleState = await page.evaluate(async () => {
      const response = await fetch('/api/schedule', { credentials: 'same-origin' })
      const result = (await response.json()) as { channels: Array<{ platform: string; enabled: boolean; blockedReason: string | null }> }
      return result.channels
    })
    expect(scheduleState.every((channel) => !channel.enabled)).toBe(true)
    const start = await newDraft.getByLabel('Start date').inputValue()
    expect(start).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    await newDraft.getByRole('button', { name: 'Generate draft' }).click()
    const preview = page.getByTestId('draft-preview')
    await expect(preview).toBeVisible({ timeout: 30_000 })
    await expect(preview.getByTestId('draft-summary')).toContainText(/\d+ of \d+ requested slots? fillable/)
    await expect(preview.getByTestId('job-time').first()).toBeVisible()
    await expect(preview.getByRole('article').first().getByText('Exact caption')).toBeVisible()
    const presetSha = (await preview.getByRole('heading', { level: 2 }).textContent())?.replace('Draft ', '').trim() ?? ''
    expect(presetSha).toMatch(/^[0-9a-f]{8}$/)

    // Customize retains the same exact inputs and draft identity; no schedule approval is submitted.
    await newDraft.getByText('Customize').click()
    const form = newDraft.getByTestId('generator-form')
    await expect(form.getByLabel('Timezone (IANA name)')).toHaveValue('America/New_York')
    await form.getByRole('button', { name: 'Generate draft' }).click()
    await expect(preview.getByRole('heading', { level: 2 })).toHaveText(`Draft ${presetSha}`)
    const approval = page.getByTestId('approval-panel')
    await expect(approval.getByRole('button', { name: 'Approve schedule' })).toBeVisible()
    await expect(approval.getByText(/Ready to approve\.|channel|blocked|not verified/i)).toBeVisible()

    // Publish destinations retain the draft while switching to confirmed-only history and back.
    await page.getByRole('navigation', { name: 'Publishing views' }).getByRole('link', { name: 'Published' }).click()
    await expect(page.getByRole('navigation', { name: 'Publishing views' }).getByRole('link', { name: 'Published' })).toHaveAttribute('aria-current', 'page')
    await expect(page.getByTestId('history-results')).toBeVisible()
    await page.getByRole('navigation', { name: 'Publishing views' }).getByRole('link', { name: 'Upcoming' }).click()
    await expect(page.getByTestId('draft-preview').getByRole('heading', { level: 2 })).toContainText(presetSha)
    await checkLayout(page, 'draft preview; approval not submitted')

    // Activity: one timeline with severity labels, chips instead of selects, a search box and a closed ⋯ menu.
    await openUtility(page, 'Operations')
    await expect(page.getByRole('heading', { level: 1, name: 'Activity' })).toBeVisible()
    const feed = page.getByTestId('activity-feed')
    const entries = feed.getByTestId('activity-entry')
    await expect(entries.first()).toBeVisible()
    expect(await entries.count()).toBeGreaterThan(3)
    await expect(entries.first()).toContainText(/Error|Warning|Success|Info/)
    await expect(entries.first().locator('time')).toHaveText(/\d{2}:\d{2} \S+ · (\w{3} \d{1,2} \w{3}, )?\d{2}:\d{2} UTC/)
    await expect(page.getByText(/^Updated \d{2}:\d{2}:\d{2}/)).toBeVisible()
    const toggle = page.getByRole('button', { name: 'Pause auto-refresh' })
    await toggle.click()
    await expect(page.getByRole('button', { name: 'Resume auto-refresh' })).toBeVisible()
    await page.getByRole('button', { name: 'Resume auto-refresh' }).click()
    await expect(page.getByLabel('Platform')).toBeHidden()
    await checkLayout(page, 'activity')

    // Posts (the old History) is a chip; each post opens its job detail drawer.
    const chips = page.getByRole('group', { name: 'Show' })
    await chips.getByRole('button', { name: 'Posts' }).click()
    await expect(chips.getByRole('button', { name: 'Posts' })).toHaveAttribute('aria-pressed', 'true')
    const results = page.getByTestId('history-results')
    await expect(results.getByText(/\d+ jobs?\.|Showing \d+ of \d+ jobs\./)).toBeVisible()
    const post = results.getByTestId('post-entry').first()
    await expect(post).toBeVisible()
    await post.getByRole('button', { name: /^Details/ }).click()
    const drawer = page.getByRole('dialog')
    await expect(drawer).toBeVisible()
    await expect(drawer.getByRole('heading', { name: 'Events' })).toBeVisible()
    await drawer.getByRole('button', { name: 'Close' }).click()
    await checkLayout(page, 'activity posts')

    // Settings: Pause is here; resuming is only the owner's activation command.
    await openUtility(page, 'Settings')
    await expect(page.getByRole('heading', { level: 1, name: 'Settings' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Pause publishing' })).toBeVisible()
    await expect(page.getByRole('heading', { level: 2, name: 'Activation' })).toBeVisible()
    await checkLayout(page, 'settings')

    // The old History hash redirects to the Posts chip.
    await page.goto('/#/history')
    await expect(page).toHaveURL(/#\/activity\?tab=posts$/)
    await expect(page.getByRole('heading', { level: 1, name: 'Activity' })).toBeVisible()
    await expect(page.getByTestId('history-results')).toBeVisible()
  })
})
