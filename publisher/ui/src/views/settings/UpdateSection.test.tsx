import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiRequestError } from '../../api/client'
import { ORIGIN, RUNNING, updateInfo } from '../../test/fixtures'
import type { UnitsApply } from '../../api/types'
import { BASELINE_KEY, readBaseline, unitsApplyState, UPDATED_KEY } from '../../lib/update'
import { UpdateSection } from './UpdateSection'

const { api } = vi.hoisted(() => ({ api: { updateStatus: vi.fn(), updateCheck: vi.fn(), updateStart: vi.fn() } }))
vi.mock('../../api/client', async (importOriginal) => ({ ...(await importOriginal<typeof import('../../api/client')>()), api }))

describe('UpdateSection', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.setSystemTime(new Date('2026-10-20T12:00:00Z'))
    api.updateStatus.mockReset().mockResolvedValue(updateInfo())
    api.updateCheck.mockReset().mockResolvedValue({ queued: true })
    api.updateStart.mockReset().mockResolvedValue({ queued: true })
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows installed vs latest and submits the reviewed full SHA after confirmation', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<UpdateSection reloadPage={vi.fn()} />)
    const section = await screen.findByTestId('update-section')
    await within(section).findByText('2 updates available.')
    expect(within(section).getByText(RUNNING.slice(0, 7))).toBeInTheDocument()
    expect(within(section).getAllByText(ORIGIN.slice(0, 7)).length).toBeGreaterThan(0)
    expect(within(section).getByText(/ui: add the guide/)).toBeInTheDocument()

    await user.click(within(section).getByRole('button', { name: 'Update' }))
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent(ORIGIN)
    const confirm = within(dialog).getByRole('button', { name: 'Update' })
    expect(confirm).toBeEnabled()
    await user.click(confirm)
    await waitFor(() => expect(api.updateStart).toHaveBeenCalledWith(ORIGIN))
    expect(readBaseline()).toMatchObject({ runningCommit: RUNNING })
  })

  it('cancellation queues nothing and an expired check disables the pinned target', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime })
    render(<UpdateSection reloadPage={vi.fn()} />)
    const section = await screen.findByTestId('update-section')
    await within(section).findByText('2 updates available.')
    await user.click(within(section).getByRole('button', { name: 'Update' }))
    const dialog = screen.getByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }))
    expect(api.updateStart).not.toHaveBeenCalled()
    await user.click(within(section).getByRole('button', { name: 'Update' }))
    const pinned = screen.getByRole('dialog')
    await act(async () => { await vi.advanceTimersByTimeAsync(16 * 60_000) })
    expect(within(pinned).getByRole('button', { name: 'Update' })).toBeDisabled()
    expect(pinned).toHaveTextContent(ORIGIN)
    expect(api.updateStart).not.toHaveBeenCalled()
  })

  it('polls while updating, shows Restarting when unreachable, and reloads once the running commit changes', async () => {
    sessionStorage.setItem(BASELINE_KEY, JSON.stringify({ runningCommit: RUNNING, startedAt: Date.now(), statusUpdatedAt: '2026-10-20T11:55:00Z' }))
    const reloadPage = vi.fn()
    api.updateStatus
      .mockResolvedValueOnce(updateInfo({ status: { phase: 'staging' } }))
      .mockResolvedValueOnce(updateInfo({ status: { phase: 'staging' } }))
      .mockRejectedValueOnce(new ApiRequestError(502, 'Bad gateway', null))
      .mockResolvedValue(updateInfo({ runningCommit: ORIGIN, repoHead: ORIGIN, status: { phase: 'complete' } }))
    render(<UpdateSection reloadPage={reloadPage} />)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100)
    })
    expect(screen.getByText('Downloading and testing the update…')).toBeInTheDocument()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100)
    })
    expect(screen.getByText('Restarting…')).toBeInTheDocument()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100)
    })
    await waitFor(() => expect(reloadPage).toHaveBeenCalledTimes(1))
    expect(sessionStorage.getItem(BASELINE_KEY)).toBeNull()
    expect(sessionStorage.getItem(UPDATED_KEY)).toBe(ORIGIN)
  })

  it('explains the copied install instead of offering a check', async () => {
    api.updateStatus.mockResolvedValue(updateInfo({ installKind: 'copy', runningCommit: null, check: null }))
    render(<UpdateSection reloadPage={vi.fn()} />)
    expect(await screen.findByText(/still runs the copied install/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Guide → Update the Pi' })).toHaveAttribute('href', '#/guide/update-the-pi')
    expect(screen.queryByRole('button', { name: 'Check for updates' })).toBeNull()
  })

  it('shows the units command with a copy button when unit files changed', async () => {
    api.updateStatus.mockResolvedValue(updateInfo({ unitsChanged: true, applyUnitsCommand: 'sudo /opt/scalar-social/repo/publisher/deploy/apply-units.sh' }))
    render(<UpdateSection reloadPage={vi.fn()} />)
    expect(await screen.findByText('Unit files changed')).toBeInTheDocument()
    expect(screen.getByText('sudo /opt/scalar-social/repo/publisher/deploy/apply-units.sh')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Copy command' }).length).toBeGreaterThan(0)
  })

  it('says the Pi is applying unit changes by itself, with no command to run', async () => {
    const at = new Date(Date.now() - 60_000).toISOString().replace(/\.\d+Z$/, 'Z')
    api.updateStatus.mockResolvedValue(
      updateInfo({ unitsChanged: true, applyUnitsCommand: 'sudo x', unitsApply: { phase: 'running', commit: RUNNING, at, error: null, log: [] } }),
    )
    render(<UpdateSection reloadPage={vi.fn()} />)
    expect(await screen.findByText('Applying unit file changes automatically…')).toBeInTheDocument()
    expect(screen.queryByText('Unit files changed')).toBeNull()
    expect(screen.queryByText('sudo x')).toBeNull()
  })

  it('shows a failed automatic apply with its log and the command as a fallback', async () => {
    api.updateStatus.mockResolvedValue(
      updateInfo({
        unitsChanged: true,
        applyUnitsCommand: 'sudo x',
        unitsApply: { phase: 'failed', commit: RUNNING, at: '2026-10-20T11:00:00Z', error: 'apply-units.sh stopped (exit 1).', log: ['npm ci failed'] },
      }),
    )
    render(<UpdateSection reloadPage={vi.fn()} />)
    expect(await screen.findByText('The automatic apply failed')).toBeInTheDocument()
    expect(screen.getByText(/apply-units.sh stopped \(exit 1\)/)).toBeInTheDocument()
    expect(screen.getByText('npm ci failed')).toBeInTheDocument()
    expect(screen.getByText('sudo x')).toBeInTheDocument()
  })

  it('says when the changes were applied automatically', async () => {
    api.updateStatus.mockResolvedValue(updateInfo({ unitsApply: { phase: 'ok', commit: RUNNING, at: '2026-10-20T11:00:00Z', error: null, log: [] } }))
    render(<UpdateSection reloadPage={vi.fn()} />)
    expect(await screen.findByText(/were applied automatically/)).toBeInTheDocument()
  })
})

describe('unitsApplyState', () => {
  const now = Date.parse('2026-10-20T12:00:00Z')
  const auto = (phase: UnitsApply['phase'], at = '2026-10-20T11:58:00Z'): UnitsApply => ({ phase, commit: RUNNING, at, error: null, log: [] })
  it('falls back to the manual command when nothing was queued or a queued run never started', () => {
    const changed = updateInfo({ unitsChanged: true })
    expect(unitsApplyState(changed, null, now)).toBe('manual')
    expect(unitsApplyState(changed, auto('queued'), now)).toBe('working')
    expect(unitsApplyState(changed, auto('queued', '2026-10-20T11:00:00Z'), now)).toBe('manual')
    expect(unitsApplyState(changed, auto('running'), now)).toBe('working')
    expect(unitsApplyState(changed, auto('failed'), now)).toBe('failed')
    expect(unitsApplyState(updateInfo(), auto('ok'), now)).toBe('done')
    expect(unitsApplyState(updateInfo(), null, now)).toBeNull()
  })
})
