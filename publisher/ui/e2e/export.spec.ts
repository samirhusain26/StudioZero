import { expect, test } from '@playwright/test'

/**
 * Studio › Export in the real UI (real CSP), against a fixture backend:
 *   SCALAR_UI_PASSCODE, SCALAR_UI_EXPORT_BUNDLE = a scratch batch's review/web-jobs.json (library/_dev only),
 *   SCALAR_UI_EXPORT_EPISODE = the episode to export (default: the first). SCALAR_UI_EXPORT_UPLOAD=1 also finalizes and
 *   uploads it to the fixture backend (never against real state). Needs a browser with WebCodecs H.264/AAC
 *   (SCALAR_UI_BROWSER_CHANNEL=chrome).
 */
const PASSCODE = process.env.SCALAR_UI_PASSCODE ?? ''
const BUNDLE = process.env.SCALAR_UI_EXPORT_BUNDLE ?? ''

test.describe('Studio export', () => {
  test.skip(!PASSCODE || !BUNDLE, 'Set SCALAR_UI_PASSCODE and SCALAR_UI_EXPORT_BUNDLE (scratch batch only).')
  test.setTimeout(10 * 60_000)

  test('open a bundle, preview, export one episode, it passes the checks', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'desktop', 'Laptop flow (phones export one episode at a time by hand).')
    await page.goto('/')
    await page.getByLabel('Passcode').fill(PASSCODE)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await page.getByRole('navigation', { name: 'Sections' }).getByRole('link', { name: 'Studio', exact: true }).click()
    await page.getByRole('link', { name: 'Preview and export a batch →' }).click()
    await expect(page.getByRole('heading', { level: 1, name: 'Export' })).toBeVisible()
    await expect(page.getByTestId('step-line')).toHaveText(/^Step 1 of 6 · Make/)
    await page.getByLabel('Job bundle (web-jobs.json)').setInputFiles(BUNDLE)
    await expect(page.getByTestId('bundle-summary')).toContainText(/Batch \S+ · \d+ episodes/)
    await expect(page.getByText('This browser can export H.264 + AAC at 1080 × 1920.')).toBeVisible({ timeout: 30_000 })

    const rows = page.getByTestId('export-row')
    const row = process.env.SCALAR_UI_EXPORT_EPISODE ? rows.filter({ hasText: process.env.SCALAR_UI_EXPORT_EPISODE }) : rows.first()
    await row.getByRole('button', { name: 'Preview' }).click()
    await expect(row.locator('.motion-player')).toBeVisible({ timeout: 30_000 })
    await row.getByRole('button', { name: 'Close preview' }).click()
    await row.getByRole('button', { name: /^Export/ }).click()
    await expect(row.getByText('Passed checks')).toBeVisible({ timeout: 5 * 60_000 })
    await expect(row).toContainText(/-1[3-5](\.\d)? LUFS/)

    if (process.env.SCALAR_UI_EXPORT_UPLOAD === '1') {
      await page.getByRole('button', { name: /^Export (all|the remaining)/ }).click()
      await expect(page.getByRole('button', { name: 'All exported' })).toBeVisible({ timeout: 10 * 60_000 })
      await page.getByRole('button', { name: /^Finalize and upload/ }).click()
      await page.getByRole('dialog').getByRole('button', { name: 'Finalize and upload' }).click()
      await expect(page.getByTestId('upload-status')).toContainText('complete', { timeout: 5 * 60_000 })
    }
  })
})
