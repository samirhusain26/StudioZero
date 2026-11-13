import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'

const PASSCODE = process.env.SCALAR_UI_PASSCODE ?? ''
const VIDEO = process.env.SCALAR_UI_CREATION_VIDEO ?? ''
const bytes = VIDEO ? readFileSync(VIDEO) : Buffer.alloc(0)
const cut = { name: 'cut.mp4', mimeType: 'video/mp4', buffer: bytes }
const transcript = { name: 'transcript.txt', mimeType: 'text/plain', buffer: Buffer.from('Fixture quiz transcript for review.') }

async function signIn(page: Page) {
  await page.goto('/')
  await page.getByLabel('Passcode').fill(PASSCODE)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('heading', { level: 1, name: 'Studio' })).toBeVisible()
}
async function openDetails(page: Page, name: string) {
  const summary = page.locator('summary').filter({ hasText: name }).first()
  if (await summary.locator('..').getAttribute('open') === null) await summary.click()
}
async function start(page: Page, project: string) {
  await page.goto(`/#/studio/create?project=${project}`)
  await page.getByLabel('Brief', { exact: false }).fill(`Fixture ${project} story with real supplied footage.`)
  await page.getByRole('button', { name: 'Save brief and prepare prompt' }).click()
  await expect(page).toHaveURL(/production=prod-/)
  return new URLSearchParams(page.url().split('?')[1]).get('production') ?? ''
}
function manifest(id: string, project: string, revisionId: string, multiple = false) {
  const artifacts = [cut, transcript, ...(multiple ? [{ ...cut, name: 'second.mp4' }] : [])]
  return {
    productionId: id, project, revisionId, batchId: null, episodeId: null,
    files: artifacts.map((a) => ({ path: a.name, size: a.buffer.length, sha256: createHash('sha256').update(a.buffer).digest('hex'), mediaType: a.mimeType, role: a.mimeType === 'video/mp4' ? 'video' : 'transcript' })),
  }
}
async function selectReturn(page: Page, returned: ReturnType<typeof manifest>, multiple = false) {
  await openDetails(page, 'Prompt, research and return files')
  await page.getByLabel('Returned manifest.json').setInputFiles({ name: 'manifest.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(returned)) })
  // Picker order deliberately differs from manifest order: retries must remain idempotent.
  await page.getByLabel('Files listed in the manifest').setInputFiles([transcript, ...(multiple ? [{ ...cut, name: 'second.mp4' }] : []), cut])
  await page.getByRole('button', { name: 'Validate and review cut' }).click()
}

test.describe('StudioZero creation and review', () => {
  test.skip(!PASSCODE || !VIDEO, 'Run against the isolated UI fixture server with a real MP4.')

  test('brief, real playback, failed replacement, revision feedback, multicut and approval', async ({ page }) => {
    await signIn(page)
    await expect(page.locator('.project-card')).toHaveCount(4)
    const id = await start(page, 'scalargame')
    await page.getByRole('button', { name: 'Copy prompt' }).click()
    await openDetails(page, 'Prompt text and manual copy')
    await expect(page.getByLabel('Prompt', { exact: true })).toHaveValue(new RegExp(id))
    const first = manifest(id, 'scalargame', 'rev-e2e-1')
    await selectReturn(page, first)
    await expect(page.getByRole('heading', { name: 'Current cut · v1' })).toBeVisible({ timeout: 60_000 })
    const player = page.locator('video.creation-video').first()
    await expect(player).toHaveAttribute('src', /\/media\/rev-e2e-1\/cut\.mp4/)
    await expect.poll(() => player.evaluate((v: HTMLVideoElement) => v.readyState), { timeout: 15_000 }).toBeGreaterThanOrEqual(1)
    await player.evaluate(async (v: HTMLVideoElement) => { v.muted = true; await v.play() })
    await expect.poll(() => player.evaluate((v: HTMLVideoElement) => v.currentTime)).toBeGreaterThan(0)
    await player.evaluate((v: HTMLVideoElement) => v.pause())
    const media = await page.request.get((await player.getAttribute('src')) ?? '', { headers: { Range: 'bytes=0-1023' } })
    expect(media.status()).toBe(206)
    // Exact retry does not create a second revision, regardless of file-picker order.
    await selectReturn(page, first)
    await expect(page.getByRole('heading', { name: 'Current cut · v1' })).toBeVisible()
    await page.getByRole('button', { name: 'Approve this cut' }).click()
    await expect(page.getByText('Cut approved for this revision', { exact: true })).toBeVisible()
    const invalid = manifest(id, 'scalargame', 'rev-invalid')
    invalid.files = invalid.files.map((file, index) => index === 0 ? { ...file, sha256: '0'.repeat(64) } : file)
    await selectReturn(page, invalid)
    await expect(page.getByRole('alert')).toContainText('Manifest size, hash')
    await expect(page.getByText('Cut approved for this revision', { exact: true })).toBeVisible()
    await expect(player).toHaveAttribute('src', /rev-e2e-1/)
    await page.getByLabel('Feedback or change request').fill('Tighten the opening by one second.')
    await page.getByRole('button', { name: 'Request revision' }).click()
    await openDetails(page, 'Prompt, research and return files')
    await openDetails(page, 'Prompt text and manual copy')
    await expect(page.getByLabel('Prompt', { exact: true })).toHaveValue(/Tighten the opening by one second/)
    await selectReturn(page, manifest(id, 'scalargame', 'rev-e2e-2', true), true)
    await expect(page.getByRole('heading', { name: 'Current cut · v2' })).toBeVisible()
    await expect(page.getByText('Cut approved for this revision', { exact: true })).toHaveCount(0)
    await page.getByRole('button', { name: 'Cut 2', exact: true }).click()
    await expect(player).toHaveAttribute('src', /second\.mp4/)
    await page.getByRole('button', { name: 'Approve all 2 cuts' }).click()
    await expect(page.getByText('Cut approved for this revision', { exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByRole('button', { name: 'Approve all 2 cuts' })).toBeDisabled()
    await openDetails(page, 'Files, transcript and evidence')
    await expect(page.getByRole('link', { name: 'transcript.txt' })).toBeVisible()
    await openDetails(page, 'Revision history and playback')
    await openDetails(page, 'v1 · rev-e2e-1')
    const previous = page.getByLabel('Video revision rev-e2e-1: cut.mp4')
    await expect(previous).toBeVisible()
    await previous.evaluate((v: HTMLVideoElement) => v.load())
    await expect.poll(() => previous.evaluate((v: HTMLVideoElement) => v.readyState)).toBeGreaterThanOrEqual(1)
    for (const width of [320, 375, 390]) {
      await page.setViewportSize({ width, height: 812 })
      expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0)
      await page.getByLabel('Feedback or change request').scrollIntoViewIfNeeded()
      await expect(page.getByLabel('Feedback or change request')).toBeInViewport()
    }
  })

  test('draft survives reload and save failure; clipboard and missing-production states are honest', async ({ page }) => {
    await signIn(page)
    await page.goto('/#/studio/create?project=scalargame')
    await page.getByLabel('Brief', { exact: false }).fill('Saved locally while disconnected.')
    await openDetails(page, 'Optional details')
    await page.getByLabel('Working title').fill('Offline draft')
    await page.getByLabel('Creative preferences').fill('A quiet opening.')
    await page.route('**/api/creation', (route) => route.request().method() === 'POST' ? route.abort('internetdisconnected') : route.continue())
    await page.getByRole('button', { name: 'Save brief and prepare prompt' }).click()
    await expect(page.getByRole('alert')).toBeVisible()
    await page.reload()
    await expect(page.getByLabel('Brief', { exact: false })).toHaveValue('Saved locally while disconnected.')
    await openDetails(page, 'Optional details')
    await expect(page.getByLabel('Working title')).toHaveValue('Offline draft')
    await expect(page.getByLabel('Creative preferences')).toHaveValue('A quiet opening.')
    await page.unroute('**/api/creation')
    await page.getByRole('button', { name: 'Save brief and prepare prompt' }).click()
    await expect(page).toHaveURL(/production=prod-/)
    await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: () => Promise.reject(new Error('denied')) } }))
    await page.getByRole('button', { name: 'Copy prompt' }).click()
    await expect(page.getByText(/Clipboard access failed/)).toBeVisible()
    await openDetails(page, 'Prompt text and manual copy')
    await expect(page.getByLabel('Prompt', { exact: true })).toHaveValue(/Offline draft/)
    await page.goto('/#/studio/create?project=scalargame&production=missing-fixture-production')
    await expect(page.getByText('This production could not be loaded.', { exact: false })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Save brief and prepare prompt' })).toHaveCount(0)
    // A committed POST with a lost response must recover once, then permit another brief.
    await page.goto('/#/studio/create?project=explainers')
    await page.getByLabel('Brief', { exact: false }).fill('Recover this saved research question.')
    await page.route('**/api/creation', async (route) => {
      if (route.request().method() !== 'POST') return route.continue()
      await route.fetch()
      await route.abort('failed')
    })
    await page.getByRole('button', { name: 'Save brief and prepare prompt' }).click()
    await expect(page.getByRole('alert')).toBeVisible()
    await page.unroute('**/api/creation')
    await page.reload()
    await expect(page.getByText('Recovered your saved production from the server.')).toBeVisible()
    await expect(page.getByLabel('Original question')).toHaveValue('Recover this saved research question.')
    await page.goto('/#/home')
    await page.goto('/#/studio/create?project=explainers')
    await expect(page.getByRole('button', { name: 'Save brief and prepare prompt' })).toBeVisible()
    await expect(page.getByLabel('Brief', { exact: false })).toHaveValue('')
  })

  test('Explainers research gate, Originals hold and Marathon manual delivery remain separate', async ({ page }) => {
    await signIn(page)
    const explainId = await start(page, 'explainers')
    await expect(page.locator('video')).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Accept research before returning a cut' })).toBeDisabled()
    await page.getByLabel('Proposed angle').fill('Explain only the principle supported by the provided source.')
    await page.getByRole('button', { name: 'Hold topic' }).click()
    await expect(page.getByText('Saved decision: held')).toBeVisible()
    await page.getByLabel('Source URLs, one per line').fill('https://example.org/fixture-evidence')
    await page.getByRole('button', { name: 'Accept research', exact: true }).click()
    await expect(page.getByText('Saved decision: accepted')).toBeVisible()
    await openDetails(page, 'Prompt text and manual copy')
    await expect(page.getByLabel('Prompt', { exact: true })).toHaveValue(/Explain only the principle supported/)
    await expect(page.getByLabel('Prompt', { exact: true })).toHaveValue(/https:\/\/example.org\/fixture-evidence/)
    await selectReturn(page, manifest(explainId, 'explainers', 'rev-evidence'))
    await expect(page.getByRole('heading', { name: 'Current cut · v1' })).toBeVisible()
    await page.getByRole('button', { name: 'Approve this cut' }).click()
    await expect(page.getByText(/Download the reviewed files above for local delivery/)).toBeVisible()
    await expect(page.getByRole('link', { name: 'Import finalized publishing package' })).toHaveCount(0)
    await start(page, 'originals')
    await expect(page.getByText('Originals is on hold. No artifacts can be imported and no paid work is available.')).toBeVisible()
    await expect(page.getByLabel('Returned manifest.json')).toHaveCount(0)
    const weekId = await start(page, 'marathon')
    await selectReturn(page, manifest(weekId, 'marathon', 'rev-week'))
    await expect(page.getByRole('heading', { name: 'Current cut · v1' })).toBeVisible()
    await page.getByRole('button', { name: 'Approve this cut' }).click()
    await page.getByRole('button', { name: 'Record owner-reported delivery' }).click()
    await expect(page.getByText(/Owner reported delivery on/)).toBeVisible()
    await page.reload()
    await expect(page.getByText(/Owner reported delivery on/)).toBeVisible()
    await expect(page.getByRole('link', { name: 'Import finalized publishing package' })).toHaveCount(0)
  })
})
