import { expect, test, type Page } from '@playwright/test'

/**
 * Mobile smoke test (375×812) against a backend with fixture state:
 *   SCALAR_UI_URL       (default http://127.0.0.1:8765)
 *   SCALAR_UI_PASSCODE  (required)
 *   SCALAR_UI_ALLOW_APPROVE=1 to actually click Approve (never against real state).
 */
const PASSCODE = process.env.SCALAR_UI_PASSCODE ?? ''
const LOCAL_AND_UTC = /\d{2}:\d{2} \S+ · (\w{3} \d{1,2} \w{3}, )?\d{2}:\d{2} UTC/

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

/** Jump with the section nav (bottom tab bar on phones, sidebar on desktop); every screen says its loop step. */
async function open(page: Page, label: string) {
  const link = page.getByRole('navigation', { name: 'Sections' }).getByRole('link', { name: label, exact: true })
  await link.click()
  await expect(link).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('heading', { level: 1, name: label })).toBeVisible()
  await expect(page.getByTestId('step-line')).toHaveText(/^Step [1-6] of 6 · /)
}

test.describe('Scalar publishing UI smoke', () => {
  test.skip(!PASSCODE, 'Set SCALAR_UI_PASSCODE to run the smoke test against a fixture backend.')

  test('sign in → home → library → schedule draft → activity → posts', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText(/Backend reachable/)).toBeVisible()
    await checkLayout(page, 'passcode')
    await page.getByLabel('Passcode').fill(PASSCODE)
    await page.getByRole('button', { name: 'Sign in' }).click()

    // Home: the loop first (six steps, one current step with its action), then one row per platform with three marks.
    await expect(page.getByRole('heading', { level: 1, name: 'Home' })).toBeVisible()
    await expect(page.getByTestId('step-line')).toHaveText(/^Step [1-6] of 6 · /)
    const loop = page.getByRole('region', { name: 'Your loop' })
    await expect(loop.getByRole('button', { name: /^Step \d, / })).toHaveCount(6)
    await expect(loop.getByTestId('next-step')).toContainText(/^Step [1-6] · /)
    const platforms = page.getByRole('region', { name: 'Platforms' })
    await expect(platforms.getByTestId('platform-row')).toHaveCount(7)
    await expect(platforms.getByTestId('platform-row').first().getByRole('img')).toHaveCount(3)
    await checkLayout(page, 'home')

    // Library: chips instead of selects; one tap on a card opens its review screen with a playable video.
    await open(page, 'Library')
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
    await expect(page).toHaveURL(/#\/library\/make$/)
    await expect(page.getByRole('heading', { level: 1, name: 'Make a batch' })).toBeVisible()
    await expect(page.getByTestId('make-checklist').getByRole('checkbox')).toHaveCount(5)
    await checkLayout(page, 'make a batch')

    // Schedule: preset first. The proposal is shown; only Generate (or Customize) turns it into inputs.
    await open(page, 'Schedule')
    const newDraft = page.getByTestId('new-draft')
    await expect(newDraft.getByTestId('generator-form')).toHaveCount(0)
    await expect(newDraft.getByTestId('preset-times')).toContainText(/\w+ \d{2}:\d{2}/)
    const start = await newDraft.getByLabel('Start date').inputValue()
    expect(start).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    await newDraft.getByRole('button', { name: 'Generate draft' }).click()
    const preview = page.getByTestId('draft-preview')
    await expect(preview).toBeVisible({ timeout: 30_000 })
    await expect(preview.getByTestId('draft-summary')).toContainText(/\d+ of \d+ requested slots? fillable/)
    const times = preview.getByTestId('job-time')
    await expect(times.first()).toBeVisible()
    await expect(times.first()).toHaveText(LOCAL_AND_UTC)
    await checkLayout(page, 'schedule draft')
    const presetSha = (await preview.getByRole('heading', { level: 2 }).textContent())?.replace('Draft ', '').trim() ?? ''
    expect(presetSha).toMatch(/^[0-9a-f]{8}$/)

    // Same hash three ways: the preset, Customize (form filled with the preset) and the old form's inputs typed by hand.
    await newDraft.getByText('Customize').click()
    const form = newDraft.getByTestId('generator-form')
    await expect(form.getByLabel('Timezone (IANA name)')).toHaveValue('America/New_York')
    await form.getByRole('button', { name: 'Generate draft' }).click()
    await expect(preview.getByRole('heading', { level: 2 })).toHaveText(`Draft ${presetSha}`)
    const blocked = await page.evaluate(async () => {
      const r = await fetch('/api/schedule', { credentials: 'same-origin' })
      const body = (await r.json()) as { channels: { platform: string; blockedReason: string | null }[] }
      return body.channels.filter((c) => c.blockedReason).map((c) => c.platform)
    })
    const presetTimes: Record<string, string> = { threads: '09:00', x: '09:30', bluesky: '10:30', facebook: '12:15', youtube: '16:00', instagram: '18:00', tiktok: '19:00' }
    const handPlatforms: Record<string, unknown> = {}
    const minGapHours: Record<string, number> = {}
    for (const p of ['instagram', 'facebook', 'threads', 'x', 'youtube', 'bluesky', 'tiktok'].filter((p) => !blocked.includes(p))) {
      handPlatforms[p] = { include: true, weekdays: [0, 1, 2, 3, 4, 5, 6], times: [presetTimes[p]], maxPerDay: 1 }
      minGapHours[p] = 2
    }
    const end = new Date(`${start}T00:00:00Z`)
    end.setUTCDate(end.getUTCDate() + 20)
    const byHand = {
      timezone: 'America/New_York', startDate: start, endDate: end.toISOString().slice(0, 10), platforms: handPlatforms, minGapHours,
      staggerMinutes: 0, ordering: 'game-round-robin', companions: { firstComment: true, answerReply: true }, edits: {},
    }
    const handSha = await page.evaluate(async (inputs) => {
      const r = await fetch('/api/schedule/drafts', {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-Scalar-Request': '1' }, body: JSON.stringify(inputs),
      })
      return ((await r.json()) as { sha256: string }).sha256
    }, byHand)
    expect(handSha.slice(0, 8)).toBe(presetSha)

    // Typed confirmation enables Approve.
    const panel = page.getByTestId('approval-panel')
    const approve = panel.getByRole('button', { name: 'Approve schedule' })
    await expect(approve).toBeDisabled()
    const phrase = (await panel.locator('code.phrase').textContent())?.trim() ?? ''
    expect(phrase).toMatch(/^APPROVE [0-9a-f]{8}$/)
    await panel.getByLabel(/to confirm/).fill(phrase.toLowerCase())
    await expect(approve).toBeDisabled()
    await panel.getByLabel(/to confirm/).fill(phrase)
    await expect(approve).toBeEnabled()
    if (process.env.SCALAR_UI_ALLOW_APPROVE === '1') {
      await approve.click()
      await expect(panel.getByText(/Request pending|Manifest ready|Bound|Validated|Failed/)).toBeVisible({ timeout: 30_000 })
    }

    // Activity: one timeline with severity labels, chips instead of selects, a search box and a closed ⋯ menu.
    await open(page, 'Activity')
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
    await open(page, 'Settings')
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
