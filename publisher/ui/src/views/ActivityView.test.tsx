import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ActivityEntry, ActivityResponse, HistoryResponse } from '../api/types'
import { ActivityItem, ActivityView } from './ActivityView'

const activity = vi.fn<(q: unknown) => Promise<ActivityResponse>>()
const history = vi.fn<(q: unknown) => Promise<HistoryResponse>>()
vi.mock('../api/client', () => ({
  api: {
    activity: (q: unknown) => activity(q),
    history: (q: unknown) => history(q),
    exportActivity: vi.fn(),
    exportHistory: vi.fn(),
    job: vi.fn(() => new Promise(() => {})),
  },
  ApiRequestError: class extends Error {},
  waitText: () => '',
}))

const entry = (id: string, title: string, over = {}) => ({
  id, at: '2026-10-07T13:00:00Z', kind: 'library' as const, event: 'library.batch', severity: 'info' as const, title, detail: '', platform: null,
  accountId: null, jobId: null, episode: null, episodeId: null, game: null, jobKind: null, permalink: null, draftSha256: null, manifestSha256: null,
  batchId: '2026-10-b01', ...over,
})

beforeEach(() => {
  activity.mockReset()
  history.mockReset()
  activity.mockResolvedValue({ displayTimezone: 'UTC', entries: [entry('2|a', 'Batch 2026-10-b01 uploaded'), entry('1|b', 'Schedule approved', { kind: 'approval', batchId: null })], nextBefore: null } as ActivityResponse)
  history.mockResolvedValue({ displayTimezone: 'UTC', rows: [], total: 0, truncated: false })
})

describe('Activity', () => {
  it('shows chips (single select), a search box and a closed ⋯ menu: no other visible form fields', async () => {
    const onTab = vi.fn()
    render(<ActivityView tab="all" onTab={onTab} />)
    const chips = within(screen.getByRole('group', { name: 'Show' })).getAllByRole('button')
    expect(chips.map((c) => [c.textContent, c.getAttribute('aria-pressed')])).toEqual([
      ['All', 'true'], ['Posts', 'false'], ['Uploads', 'false'], ['Approvals', 'false'], ['System', 'false'],
    ])
    expect(screen.getByRole('searchbox')).toBeVisible()
    expect(screen.getByLabelText('Platform').closest('details')).not.toHaveAttribute('open')
    await userEvent.setup().click(chips[2] as HTMLElement)
    expect(onTab).toHaveBeenCalledWith('uploads')
    expect(await screen.findByText('Batch 2026-10-b01 uploaded')).toBeInTheDocument()
  })

  it('maps chips to activity kinds', async () => {
    render(<ActivityView tab="system" onTab={vi.fn()} />)
    await waitFor(() => expect(activity).toHaveBeenCalledWith({ kind: 'system', limit: 100 }))
  })

  it('searches loaded entries', async () => {
    render(<ActivityView tab="all" onTab={vi.fn()} />)
    expect(await screen.findByText('Schedule approved')).toBeInTheDocument()
    await userEvent.setup().type(screen.getByRole('searchbox'), 'b01{Enter}')
    expect(screen.queryByText('Schedule approved')).toBeNull()
    expect(screen.getByText('Batch 2026-10-b01 uploaded')).toBeInTheDocument()
  })

  it('Posts is the old History, and an empty one points to the owner’s activation command', async () => {
    render(<ActivityView tab="posts" onTab={vi.fn()} />)
    await waitFor(() => expect(history).toHaveBeenCalledWith({}))
    const results = await screen.findByTestId('history-results')
    expect(await within(results).findByText('0 jobs.')).toBeInTheDocument()
    expect(within(results).getByRole('link', { name: 'Settings › Activation →' })).toHaveAttribute('href', '#/settings#activation')
    expect(activity).not.toHaveBeenCalled()
  })
})

const jobEntry: ActivityEntry = {
  id: '2026-10-07T13:00:00Z|j:000000000004', at: '2026-10-07T13:00:00Z', kind: 'job', event: 'job.uncertain', severity: 'warning',
  title: 'Result unknown; the Pi is checking the platform', detail: 'Result unknown, checking.', platform: 'threads', accountId: 't-1',
  jobId: 'b'.repeat(24), episode: 'scalar:Q2:clues', episodeId: 'scalar-clues-002', game: 'scalar', jobKind: 'post', permalink: null,
  draftSha256: null, manifestSha256: null, batchId: null,
}

describe('ActivityItem', () => {
  it('shows local time with UTC, a text severity label, and opens the job', async () => {
    const onOpen = vi.fn()
    render(
      <ol>
        <ActivityItem entry={jobEntry} zone="America/New_York" onOpenJob={onOpen} />
      </ol>,
    )
    expect(screen.getByText('09:00 EDT · 13:00 UTC')).toBeInTheDocument()
    expect(screen.getByText('Warning')).toBeInTheDocument()
    await userEvent.setup().click(screen.getByRole('button', { name: jobEntry.title }))
    expect(onOpen).toHaveBeenCalledWith(jobEntry.jobId)
  })

  it('renders entries without a job as plain text', () => {
    render(
      <ol>
        <ActivityItem entry={{ ...jobEntry, jobId: null, severity: 'success', title: 'Monitor finished OK' }} zone="UTC" onOpenJob={vi.fn()} />
      </ol>,
    )
    expect(screen.queryByRole('button')).toBeNull()
    expect(screen.getByText('Success')).toBeInTheDocument()
  })
})
