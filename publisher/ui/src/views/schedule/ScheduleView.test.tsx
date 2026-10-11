import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ChannelSummary, Platform, QueueJob, ScheduleResponse } from '../../api/types'
import { ApprovedSchedule, NewDraft } from './ScheduleView'

const channel = (platform: Platform, blockedReason: string | null = null): ChannelSummary => ({
  platform, accountId: 'acct', route: 'buffer', enabled: blockedReason === null, identityVerified: true, publishingVerified: true, blockedReason, profileUrl: null,
})
const channels = [channel('threads'), channel('instagram'), channel('tiktok', 'No API route'), channel('facebook', 'Not authenticated')]

describe('New draft (preset first)', () => {
  it('shows the recommended plan with two visible fields; form state stays empty until a tap', async () => {
    const onGenerate = vi.fn()
    render(<NewDraft channels={channels} busy={false} onGenerate={onGenerate} />)
    const card = screen.getByTestId('new-draft')
    expect((within(card).getByLabelText('Start date') as HTMLInputElement).value).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    expect(card).toHaveTextContent('America/New_York')
    expect(screen.getByTestId('preset-times')).toHaveTextContent('Threads 09:00 · X 09:30 · Bluesky 10:30 · YouTube 16:00 · Instagram 18:00')
    expect(card).toHaveTextContent('Blocked today: TikTok (No API route) · Facebook (Not authenticated)')
    // Visible fields: the start date, and the timezone behind Change. The per-platform form is not rendered yet.
    expect(within(card).queryByTestId('generator-form')).toBeNull()
    expect(card.querySelectorAll('input, select, textarea')).toHaveLength(1)
    expect(onGenerate).not.toHaveBeenCalled()

    await userEvent.setup().click(within(card).getByRole('button', { name: 'Generate draft' }))
    expect(onGenerate).toHaveBeenCalledTimes(1)
    const inputs = onGenerate.mock.calls[0]?.[0]
    expect(inputs.timezone).toBe('America/New_York')
    expect(Object.keys(inputs.platforms).sort()).toEqual(['bluesky', 'instagram', 'threads', 'x', 'youtube'])
    expect(inputs.companions).toEqual({ firstComment: true, answerReply: true })
  })

  it('Customize opens the existing form already filled with the preset values', async () => {
    const onGenerate = vi.fn()
    const user = userEvent.setup()
    render(<NewDraft channels={channels} busy={false} onGenerate={onGenerate} />)
    await user.click(screen.getByText('Customize'))
    const form = await screen.findByTestId('generator-form')
    expect(within(form).getByLabelText('Timezone (IANA name)')).toHaveValue('America/New_York')
    expect(within(form).getByLabelText('Include Threads')).toBeChecked()
    expect(within(form).getByLabelText('Include TikTok')).not.toBeChecked()
    expect(within(form).getByRole('list', { name: 'Instagram times' })).toHaveTextContent('18:00')
    // One primary action: the preset button gives way to the form's own Generate draft.
    expect(screen.getAllByRole('button', { name: 'Generate draft' })).toHaveLength(1)
    await user.click(within(form).getByRole('button', { name: 'Generate draft' }))
    const viaForm = onGenerate.mock.calls[0]?.[0]
    expect(Object.keys(viaForm.platforms).sort()).toEqual(['bluesky', 'instagram', 'threads', 'x', 'youtube'])
  })

  it('a changed timezone that the browser does not know is refused before anything is sent', async () => {
    const onGenerate = vi.fn()
    const user = userEvent.setup()
    render(<NewDraft channels={channels} busy={false} onGenerate={onGenerate} />)
    await user.click(screen.getByRole('button', { name: 'Change' }))
    const zone = screen.getByRole('textbox', { name: 'Timezone' })
    await user.clear(zone)
    await user.type(zone, 'Eastern')
    await user.click(screen.getByRole('button', { name: 'Generate draft' }))
    expect(onGenerate).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('“Eastern” is not a timezone this browser recognises.')
  })
})

const job = (over: Partial<QueueJob>): QueueJob => ({
  key: 'k', jobId: null, platform: 'threads', accountId: 'a', slotUtc: '2026-10-09T13:00:00Z', kind: 'post', episodeKey: 'e', parentKey: null,
  episodeId: 'scalar-clues-001', questionId: 'q', game: 'scalar', text: 't', youtube: null, coverUrl: null, status: 'not-enqueued',
  statusLabel: 'Not yet queued', dispatched: false, editable: true, lockReason: null, ...over,
} as QueueJob)

describe('Approved schedule card', () => {
  const base: ScheduleResponse = {
    displayTimezone: 'America/New_York',
    manifest: { sha256: '3f9a12c0'.padEnd(64, '0'), draftSha256: 'a'.repeat(64), approvedAt: '2026-10-08T01:40:00Z', scope: ['threads', 'x'], bound: true, jobCount: 3 },
    jobs: [
      job({ key: '1', slotUtc: '2026-10-09T13:00:00Z' }),
      job({ key: '2', platform: 'x', slotUtc: '2026-10-09T13:30:00Z' }),
      job({ key: '3', slotUtc: '2026-10-29T13:00:00Z' }),
      job({ key: '4', kind: 'comment', slotUtc: '2026-10-09T13:02:00Z' }),
    ],
    pendingRequest: null, lastResult: null, channels: [], recentDrafts: [],
  }

  it('says the span, hash, approval time and next posts, with the queue one tap away', () => {
    render(<ApprovedSchedule schedule={base} now={new Date('2026-10-08T12:00:00Z')} />)
    const card = screen.getByRole('region', { name: 'Approved schedule' })
    expect(card).toHaveTextContent('2 days · 2026-10-09 → 2026-10-29 · hash 3f9a12c0')
    expect(card).toHaveTextContent('Next: Threads Fri 9 Oct, 09:00 EDT · X Fri 9 Oct, 09:30 EDT · Threads Thu 29 Oct, 09:00 EDT')
    expect(within(card).getByRole('link', { name: 'View queue (4)' })).toHaveAttribute('href', '#/schedule/queue')
  })

  it('points back to approving episodes when nothing is approved', () => {
    render(<ApprovedSchedule schedule={{ ...base, manifest: null, jobs: [] }} />)
    expect(screen.getByRole('link', { name: 'Approve episodes first →' })).toHaveAttribute('href', '#/library')
  })
})
