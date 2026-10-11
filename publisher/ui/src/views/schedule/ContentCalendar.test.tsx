import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { ChannelSummary, LibraryEpisode, Platform, QueueJob, ScheduleResponse } from '../../api/types'
import { ContentCalendar } from './ContentCalendar'

const channel = (platform: Platform): ChannelSummary => ({
  platform, accountId: 'acct', route: 'buffer', enabled: true, identityVerified: true, publishingVerified: true, blockedReason: null, profileUrl: null,
})

const job = (over: Partial<QueueJob>): QueueJob =>
  ({
    key: 'k', jobId: null, platform: 'threads', accountId: 'acct', slotUtc: '2026-10-10T13:00:00Z', kind: 'post', episodeKey: 'e', parentKey: null,
    episodeId: 'scalar-clues-001', questionId: 'q1', game: 'scalar', text: 't', youtube: null, coverUrl: null, status: 'not-enqueued',
    statusLabel: 'Not yet queued', dispatched: false, editable: true, lockReason: null, permalink: null, error: null, ...over,
  }) as QueueJob

const schedule: ScheduleResponse = {
  displayTimezone: 'America/New_York',
  manifest: { sha256: 'a'.repeat(64), draftSha256: 'b'.repeat(64), approvedAt: '2026-10-08T00:00:00Z', scope: ['threads'], bound: true, jobCount: 2 },
  jobs: [job({ key: '1', slotUtc: '2026-10-10T13:00:00Z' }), job({ key: '2', slotUtc: '2026-10-11T13:00:00Z', questionId: 'q2', episodeId: 'scalar-clues-002' })],
  pendingRequest: null,
  lastResult: null,
  channels: [channel('threads')],
  recentDrafts: [],
}

const spare = [
  { episodeId: 'a', questionId: 'q3', status: 'approved', currentApproval: { id: 1 }, platforms: { threads: { eligible: true, reason: null } }, postedOn: [] },
  { episodeId: 'b', questionId: 'q4', status: 'approved', currentApproval: { id: 2 }, platforms: { threads: { eligible: true, reason: null } }, postedOn: [] },
] as unknown as LibraryEpisode[]

describe('Content calendar', () => {
  it('says when the queue runs out and how far the unscheduled videos reach, and lists a tapped day', async () => {
    render(<ContentCalendar schedule={schedule} episodes={spare} now={new Date('2026-10-09T16:00:00Z')} />)
    expect(screen.getByTestId('runway-summary')).toHaveTextContent('Scheduled through Sun 11 Oct. Runs out Mon 12 Oct on Threads.')
    expect(screen.getByTestId('runway-summary')).toHaveTextContent('could carry posting to Tue 13 Oct')
    expect(screen.getByTestId('runway-threads')).toHaveTextContent('Threads11 Oct2213 Oct')

    await userEvent.setup().click(screen.getByRole('button', { name: /Saturday,? 10 October 2026: 1 post/ }))
    const day = screen.getByTestId('calendar-day')
    expect(within(day).getByText('Threads')).toBeInTheDocument()
    expect(day).toHaveTextContent('scalar-clues-001')
    expect(screen.getByRole('button', { name: /Monday,? 12 October 2026: nothing scheduled; approved videos could fill it/ })).toBeInTheDocument()
  })
})
