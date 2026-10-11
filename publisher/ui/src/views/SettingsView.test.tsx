import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import type { MetricsStatus } from '../api/types'
import { JourneyContext, type JourneyState } from '../hooks/useJourney'
import { dashboardFixture } from '../test/fixtures'
import { UncertainJobs } from './settings/SystemSection'
import { SETTINGS_SECTIONS, SettingsView } from './SettingsView'

vi.mock('./settings/UpdateSection', () => ({ UpdateSection: () => <div /> }))
vi.mock('./settings/ActivationSection', () => ({ ActivationSection: () => <div /> }))

function renderSettings(onSignOut = vi.fn(), state: Partial<JourneyState> = {}) {
  const value: JourneyState = { journey: null, dashboard: dashboardFixture(), update: null, reload: vi.fn(), accept: vi.fn(), ...state }
  return render(
    <JourneyContext.Provider value={value}>
      <SettingsView onSignOut={onSignOut} />
    </JourneyContext.Provider>,
  )
}

const stats: MetricsStatus = {
  enabled: true,
  pending: null,
  lastRun: { startedAt: '2026-10-06T19:20:00Z', finishedAt: '2026-10-06T19:20:40Z', trigger: 'timer', backfill: 0, outcome: 'ok', platforms: {} },
  timer: {
    unit: 'scalar-social-metrics.timer',
    role: 'metrics',
    label: 'Post stats',
    enabled: true,
    active: true,
    lastRunAt: '2026-10-06T19:20:00Z',
    lastResult: 'success',
    lastResultDetail: null,
    nextRunAt: '2026-10-06T20:20:00Z',
  },
  pathActive: false,
}

describe('SettingsView', () => {
  beforeEach(() => {
    vi.spyOn(api, 'getMetricsStatus').mockResolvedValue(stats)
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('is one page of anchored sections in a fixed order, with an index', () => {
    const { container } = renderSettings()
    expect([...container.querySelectorAll('.stack-lg > [id]')].map((el) => el.id)).toEqual(SETTINGS_SECTIONS.map((s) => s.id))
    const index = screen.getByRole('navigation', { name: 'On this page' })
    expect(within(index).getByRole('link', { name: 'Activation' })).toHaveAttribute('href', '#/settings#activation')
    for (const name of ['Publishing control', 'System', 'Backup', 'Session']) expect(screen.getByRole('heading', { level: 2, name })).toBeInTheDocument()
  })

  it('offers Pause and points to Activation for resume', () => {
    renderSettings()
    expect(screen.getByRole('button', { name: 'Pause publishing' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /resume|unpause|enable/i })).toBeNull()
    expect(screen.getByRole('link', { name: 'see Activation' })).toHaveAttribute('href', '#/settings#activation')
  })

  it('opens System items that need attention and keeps the rest collapsed', async () => {
    renderSettings()
    const system = screen.getByTestId('system-section')
    await within(system).findByText('Post stats: hourly reads on')
    const open = [...system.querySelectorAll('details')].map((d) => [d.querySelector('summary')?.textContent, d.open])
    expect(open).toEqual([
      ['Jobs needing reconciliation (1)', true],
      ['Issues (1)', true],
      ['Timers', false],
      ['Post stats: hourly reads on', false],
      ['Health, budgets and storage', false],
    ])
  })

  it('shows the hourly post stats state in System: on/off, last run, next timer run, path unit', async () => {
    renderSettings()
    const block = screen.getByTestId('post-stats-system')
    await within(block).findByText('Post stats: hourly reads on')
    const facts = within(block).getByRole('region', { name: 'Post stats' })
    expect(facts).toHaveTextContent('Hourly readsOn')
    expect(facts).toHaveTextContent('Last runTue 6 Oct, 15:20 EDT · 19:20 UTC · by the hourly timer · ✓finished')
    expect(facts).toHaveTextContent('Next timer runTue 6 Oct, 16:20 EDT · 20:20 UTC')
    expect(facts).toHaveTextContent('not picked up: scalar-social-metrics.path is not active')
    expect(within(block).queryAllByRole('button')).toHaveLength(0)
  })

  it('keeps the session UI on screen after a failed sign out and allows retry', async () => {
    const user = userEvent.setup()
    const onSignOut = vi.fn().mockRejectedValueOnce(new Error('The Pi could not be reached.')).mockResolvedValueOnce(undefined)
    renderSettings(onSignOut)
    await user.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not sign out: The Pi could not be reached.')
    await user.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(onSignOut).toHaveBeenCalledTimes(2)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('never renders a post-again or retry action for uncertain jobs', () => {
    const data = dashboardFixture()
    render(<UncertainJobs jobs={data.uncertainJobs} zone={data.displayTimezone} />)
    const section = screen.getByRole('region', { name: 'Jobs needing reconciliation' })
    expect(within(section).queryAllByRole('button')).toHaveLength(0)
    expect(within(section).queryByText(/post again|retry|repost|re-send|resend/i)).toBeNull()
    expect(within(section).getByText('Check the X profile for this post.')).toBeInTheDocument()
    expect(within(section).getByText(/never sent again from here/i)).toBeInTheDocument()
    expect(within(section).getAllByText(/Waiting for the platform to confirm/).length).toBeGreaterThan(0)
    // Last and next check are shown with local + UTC time.
    expect(within(section).getByText('Tue 6 Oct, 16:00 EDT · 20:00 UTC')).toBeInTheDocument()
    expect(within(section).getByText('Tue 6 Oct, 17:00 EDT · 21:00 UTC')).toBeInTheDocument()
  })
})
