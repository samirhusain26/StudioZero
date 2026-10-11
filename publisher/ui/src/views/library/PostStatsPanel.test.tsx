import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiRequestError } from '../../api/client'
import type { MetricsLastRun, MetricsPlatformRun, MetricsStatus } from '../../api/types'
import { GUIDE, hasAnchor } from '../../lib/guide'
import { METRICS_POLL_MS, METRICS_WAIT_MS, YOUTUBE_KEY_COMMAND } from '../../lib/metricsStatus'
import { PostStatsPanel, STATS_GUIDE_ANCHOR } from './PostStatsPanel'

const run = (status: MetricsPlatformRun['status'], over: Partial<MetricsPlatformRun> = {}): MetricsPlatformRun => ({
  status,
  postsRead: 0,
  accountsRead: 0,
  reason: null,
  ...over,
})

const lastRun = (over: Partial<MetricsLastRun> = {}): MetricsLastRun => ({
  startedAt: '2026-10-09T13:20:00Z',
  finishedAt: '2026-10-09T13:20:40Z',
  trigger: 'timer',
  backfill: 0,
  outcome: 'ok',
  platforms: {
    instagram: run('ok', { postsRead: 3, accountsRead: 1 }),
    youtube: run('ok'),
  },
  ...over,
})

const metricsStatus = (over: Partial<MetricsStatus> = {}): MetricsStatus => ({
  enabled: true,
  pending: null,
  lastRun: lastRun(),
  timer: null,
  pathActive: true,
  ...over,
})

const pending = { requestedAt: '2026-10-09T14:00:00Z', backfill: 0 }

function platformItem(name: string): HTMLElement {
  const list = screen.getByRole('list', { name: 'Each platform in the last read' })
  const item = within(list)
    .getAllByRole('listitem')
    .find((li) => li.textContent?.startsWith(`${name}:`))
  if (!item) throw new Error(`no ${name} row`)
  return item
}

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('Post stats panel', () => {
  it('shows hourly reads off, with a plain switch and the read button', async () => {
    vi.spyOn(api, 'getMetricsStatus').mockResolvedValue(metricsStatus({ enabled: false, lastRun: null }))
    render(<PostStatsPanel zone="UTC" />)
    const toggle = await screen.findByRole('button', { name: 'Hourly reads', pressed: false })
    expect(toggle).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByText(/Hourly reads are off: the Pi reads nothing on its own/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Read stats now' })).toBeEnabled()
    expect(screen.getByText('No stats read yet.')).toBeInTheDocument()
    expect(screen.queryByText(/Waiting for the Pi/)).not.toBeInTheDocument()
  })

  it('shows hourly reads on, the last read time and the outcome in words', async () => {
    vi.spyOn(api, 'getMetricsStatus').mockResolvedValue(metricsStatus())
    render(<PostStatsPanel zone="UTC" />)
    expect(await screen.findByRole('button', { name: 'Hourly reads', pressed: true })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByText(/^Last read/)).toHaveTextContent('Last read Fri 9 Oct, 13:20 UTC · 13:20 UTC · by the hourly timer · ✓finished')
    expect(platformItem('Instagram')).toHaveTextContent('Instagram: ✓read · 3 posts, 1 account')
  })

  it.each([
    ['ok', null, 'read'],
    ['not-configured', null, 'not set up'],
    ['authorization', null, 'access refused'],
    ['rejected', null, "can't be read"],
    ['rejected', 'buffer', "can't be read (posted through Buffer)"],
    ['error', null, 'read failed'],
    ['unsupported', null, 'not readable by the Pi'],
  ] as const)('words platform status %s (reason %s) as "%s"', async (status, reason, word) => {
    vi.spyOn(api, 'getMetricsStatus').mockResolvedValue(metricsStatus({ lastRun: lastRun({ platforms: { threads: run(status, { reason }) } }) }))
    render(<PostStatsPanel zone="UTC" />)
    await screen.findByRole('button', { name: 'Hourly reads', pressed: true })
    const item = platformItem('Threads')
    expect(item.textContent?.replace(/[✓✕!•]/g, '')).toBe(`Threads: ${word}`)
  })

  it.each([
    ['stats-off', 'skipped: hourly reads are off'],
    ['bad-request', 'the read request could not be used; ask again'],
    ['error', 'failed; the Pi tries again next hour'],
  ] as const)('words the run outcome %s plainly', async (outcome, words) => {
    vi.spyOn(api, 'getMetricsStatus').mockResolvedValue(metricsStatus({ enabled: false, lastRun: lastRun({ outcome, platforms: {} }) }))
    render(<PostStatsPanel zone="UTC" />)
    await screen.findByRole('button', { name: 'Hourly reads', pressed: false })
    expect(screen.getByText(/^Last read/)).toHaveTextContent(words)
  })

  it('says so when manual reads are not picked up (path unit not active)', async () => {
    vi.spyOn(api, 'getMetricsStatus').mockResolvedValue(metricsStatus({ pathActive: false }))
    render(<PostStatsPanel zone="UTC" />)
    expect(await screen.findByText(/scalar-social-metrics\.path is not active/)).toBeInTheDocument()
  })

  it('points to the YouTube key command on the Pi, or says it is already stored', async () => {
    const get = vi.spyOn(api, 'getMetricsStatus').mockResolvedValue(metricsStatus({ lastRun: lastRun({ platforms: { youtube: run('not-configured') } }) }))
    const { unmount } = render(<PostStatsPanel zone="UTC" />)
    expect(await screen.findByText(YOUTUBE_KEY_COMMAND)).toBeInTheDocument()
    expect(screen.getByText('On the Pi')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Copy command' })).toBeInTheDocument()
    unmount()
    get.mockResolvedValue(metricsStatus())
    render(<PostStatsPanel zone="UTC" />)
    expect(await screen.findByText('YouTube key: already stored.')).toBeInTheDocument()
    expect(screen.queryByText(YOUTUBE_KEY_COMMAND)).not.toBeInTheDocument()
  })

  it('has no primary button (Copy prompt for Claude stays the one primary action)', async () => {
    vi.spyOn(api, 'getMetricsStatus').mockResolvedValue(metricsStatus({ pending, lastRun: lastRun({ platforms: { youtube: run('error') } }) }))
    const { container } = render(<PostStatsPanel zone="UTC" />)
    await screen.findByText('Waiting for the Pi…')
    expect(container.querySelectorAll('.btn-primary')).toHaveLength(0)
  })

  it('toggle sends PUT and flips aria-pressed', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'getMetricsStatus').mockResolvedValue(metricsStatus({ enabled: false }))
    const put = vi.spyOn(api, 'setMetricsEnabled').mockResolvedValue(metricsStatus({ enabled: true }))
    render(<PostStatsPanel zone="UTC" />)
    await user.click(await screen.findByRole('button', { name: 'Hourly reads', pressed: false }))
    expect(put).toHaveBeenCalledWith(true)
    expect(await screen.findByRole('button', { name: 'Hourly reads', pressed: true })).toHaveAttribute('aria-pressed', 'true')
  })

  it('reads now with a backfill, then waits for the Pi', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'getMetricsStatus').mockResolvedValue(metricsStatus())
    const post = vi.spyOn(api, 'requestMetricsRead').mockResolvedValue(metricsStatus({ pending: { ...pending, backfill: 30 } }))
    render(<PostStatsPanel zone="UTC" />)
    await screen.findByRole('button', { name: 'Hourly reads', pressed: true })
    await user.click(screen.getByText('Also read past days'))
    const input = screen.getByLabelText('Also read past days (0–93)')
    await user.clear(input)
    await user.type(input, '30')
    await user.click(screen.getByRole('button', { name: 'Read stats now' }))
    expect(post).toHaveBeenCalledWith(30)
    expect(await screen.findByText('Waiting for the Pi…')).toBeInTheDocument()
    expect(screen.getByText(/also past 30 days/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Read stats now' })).toHaveAttribute('aria-disabled', 'true')
  })

  it('reads now without a backfill sends none, and refuses an out-of-range backfill', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'getMetricsStatus').mockResolvedValue(metricsStatus())
    const post = vi.spyOn(api, 'requestMetricsRead').mockResolvedValue(metricsStatus({ pending }))
    render(<PostStatsPanel zone="UTC" />)
    await screen.findByRole('button', { name: 'Hourly reads', pressed: true })
    await user.click(screen.getByText('Also read past days'))
    const input = screen.getByLabelText('Also read past days (0–93)')
    await user.clear(input)
    await user.type(input, '120')
    await user.click(screen.getByRole('button', { name: 'Read stats now' }))
    expect(post).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('Enter a whole number of days from 0 to 93.')
    await user.clear(input)
    await user.type(input, '0')
    await user.click(screen.getByRole('button', { name: 'Read stats now' }))
    expect(post).toHaveBeenCalledWith(undefined)
  })

  it('treats 409 as an already pending read and refetches the status', async () => {
    const user = userEvent.setup()
    const get = vi
      .spyOn(api, 'getMetricsStatus')
      .mockResolvedValueOnce(metricsStatus())
      .mockResolvedValue(metricsStatus({ pending }))
    vi.spyOn(api, 'requestMetricsRead').mockRejectedValue(new ApiRequestError(409, 'A read is already waiting.', null))
    render(<PostStatsPanel zone="UTC" />)
    await user.click(await screen.findByRole('button', { name: 'Read stats now' }))
    expect(await screen.findByText('Waiting for the Pi…')).toBeInTheDocument()
    expect(get).toHaveBeenCalledTimes(2)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows the message of a 422', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'getMetricsStatus').mockResolvedValue(metricsStatus())
    vi.spyOn(api, 'requestMetricsRead').mockRejectedValue(new ApiRequestError(422, 'backfill must be 0–93 days.', null))
    render(<PostStatsPanel zone="UTC" />)
    await user.click(await screen.findByRole('button', { name: 'Read stats now' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('backfill must be 0–93 days.')
  })

  it('polls every 4 s while pending and stops when the read is done', async () => {
    vi.useFakeTimers()
    const onRead = vi.fn()
    const get = vi
      .spyOn(api, 'getMetricsStatus')
      .mockResolvedValueOnce(metricsStatus({ pending }))
      .mockResolvedValueOnce(metricsStatus({ pending }))
      .mockResolvedValue(metricsStatus({ lastRun: lastRun({ trigger: 'request', finishedAt: '2026-10-09T14:00:30Z' }) }))
    render(<PostStatsPanel zone="UTC" onRead={onRead} />)
    await act(async () => {})
    expect(screen.getByText('Waiting for the Pi…')).toBeInTheDocument()
    expect(get).toHaveBeenCalledTimes(1)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(METRICS_POLL_MS)
    })
    expect(get).toHaveBeenCalledTimes(2)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(METRICS_POLL_MS)
    })
    expect(get).toHaveBeenCalledTimes(3)
    expect(screen.queryByText('Waiting for the Pi…')).not.toBeInTheDocument()
    expect(screen.getByText(/^Last read/)).toHaveTextContent('on request')
    expect(onRead).toHaveBeenCalledTimes(1)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(METRICS_POLL_MS * 5)
    })
    expect(get).toHaveBeenCalledTimes(3)
  })

  it('stops polling after 5 minutes and says it is still waiting', async () => {
    vi.useFakeTimers()
    const get = vi.spyOn(api, 'getMetricsStatus').mockResolvedValue(metricsStatus({ pending }))
    render(<PostStatsPanel zone="UTC" />)
    await act(async () => {})
    await act(async () => {
      await vi.advanceTimersByTimeAsync(METRICS_WAIT_MS)
    })
    const calls = get.mock.calls.length
    expect(calls).toBe(METRICS_WAIT_MS / METRICS_POLL_MS + 1)
    expect(screen.queryByText('Waiting for the Pi…')).not.toBeInTheDocument()
    const still = screen.getByText(/^Still waiting for the Pi\./)
    expect(still).toHaveTextContent(
      'Still waiting for the Pi. It reads requests when scalar-social-metrics.path is installed; see Guide › Post and account stats.',
    )
    expect(within(still).getByRole('link', { name: 'Guide › Post and account stats' })).toHaveAttribute('href', `#/guide/${STATS_GUIDE_ANCHOR}`)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(METRICS_WAIT_MS)
    })
    expect(get).toHaveBeenCalledTimes(calls)
    // Check again restarts the wait.
    vi.useRealTimers()
    get.mockResolvedValue(metricsStatus())
    await userEvent.setup().click(screen.getByRole('button', { name: 'Check again' }))
    await waitFor(() => expect(screen.queryByText(/Still waiting/)).not.toBeInTheDocument())
  })

  it('links to an anchor that exists in the bundled guide', () => {
    expect(hasAnchor(GUIDE, STATS_GUIDE_ANCHOR)).toBe(true)
  })
})
