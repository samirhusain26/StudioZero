import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { DashboardResponse } from '../api/types'
import { attentionItems, platformRow } from '../lib/home'
import { journey } from '../lib/journey'
import { dashboardFixture, SHA, updateInfo } from '../test/fixtures'
import { HomeContent } from './DashboardView'

const now = new Date('2026-10-08T12:00:00Z')

function home(data: DashboardResponse = dashboardFixture(), update: ReturnType<typeof updateInfo> | null = null, onNavigate = vi.fn()) {
  const j = journey({ dashboard: data, update, make: null, now })
  if (!j) throw new Error('journey')
  return { onNavigate, ...render(<HomeContent data={data} journey={j} update={update} onNavigate={onNavigate} now={now} />) }
}

describe('Home', () => {
  it('opens with the loop: six steps and the current step expanded with one primary action', async () => {
    const { onNavigate, container } = home()
    const loop = screen.getByRole('region', { name: 'Your loop' })
    expect(container.querySelector('.stack-lg')?.firstElementChild).toBe(loop)
    const steps = within(loop).getAllByRole('button')
    expect(steps.map((b) => b.getAttribute('aria-label'))).toEqual([
      'Step 1, Make, done',
      'Step 2, Upload, done',
      'Step 3, Review, your next step',
      'Step 4, Schedule, not yet',
      'Step 5, Post, blocked',
      'Step 6, Learn, not yet',
    ])
    expect(steps.map((b) => b.textContent)).toEqual(['1Make✓', '2Upload✓', '3Review●', '4Schedule', '5Post!', '6Learn'])
    const hero = within(loop).getByTestId('next-step')
    expect(hero).toHaveTextContent('Step 3 · Review')
    expect(hero).toHaveTextContent('Review 3 episodes')
    expect(container.querySelectorAll('.btn-primary')).toHaveLength(1)
    await userEvent.setup().click(within(hero).getByRole('link', { name: 'Review 3 →' }))
    expect(onNavigate).toHaveBeenCalledWith('library')
  })

  it('shows a step’s fact when tapped: done steps their fact, blocked steps why and who', async () => {
    home()
    const user = userEvent.setup()
    const loop = screen.getByRole('region', { name: 'Your loop' })
    await user.click(within(loop).getByRole('button', { name: /^Step 2, Upload/ }))
    expect(screen.getByTestId('loop-fact')).toHaveTextContent('2 · Upload: 2026-10-b01 uploaded')
    await user.click(within(loop).getByRole('button', { name: /^Step 5, Post/ }))
    expect(screen.getByTestId('loop-fact')).toHaveTextContent('5 · Post: Paused · owner command, see Settings')
    await user.click(within(loop).getByRole('button', { name: /^Step 1, Make/ }))
    expect(screen.getByTestId('loop-fact')).toHaveTextContent('1 · Make: 2026-10-b01 · 12 episodes · 5 Oct (on the Mac)')
    expect(within(loop).getByRole('button', { name: /^Step 1, Make/ })).toHaveAttribute('aria-expanded', 'true')
    await user.click(within(loop).getByRole('button', { name: /^Step 1, Make/ }))
    expect(screen.getByTestId('loop-fact')).toBeEmptyDOMElement()
  })

  it('a blocked focus says so; nothing to do links to Activity instead of a primary button', () => {
    const d = dashboardFixture()
    const steady: DashboardResponse = {
      ...d,
      approval: { ...d.approval, manifestSha256: SHA },
      standing: { ...d.standing, awaitingReview: 0, openFeedback: 0, nextPosts: [{ at: '2026-10-09T13:00:00Z', platform: 'x', episodeId: 'e' }] },
    }
    const { unmount } = home(steady)
    expect(screen.getByTestId('next-step')).toHaveTextContent('Step 5 · Post · blocked')
    expect(screen.getByRole('link', { name: 'Open Activation →' })).toHaveAttribute('href', '#/settings#activation')
    unmount()
    const { container } = home({ ...steady, paused: false })
    expect(screen.getByTestId('next-step')).toHaveTextContent('Nothing needs you right now')
    expect(container.querySelectorAll('.btn-primary')).toHaveLength(0)
    expect(screen.getByRole('link', { name: 'See what was posted →' })).toHaveAttribute('href', '#/activity')
  })

  it('lists what needs attention, worst first, with where to deal with it', () => {
    home(dashboardFixture(), updateInfo())
    const list = screen.getByRole('region', { name: 'Attention' })
    const items = within(list).getAllByRole('listitem').map((li) => li.textContent)
    expect(items).toEqual([
      '!Check X job job12345 is uncertain and needs reconciling (owner command) → Settings › System',
      '!Check Monitor has not reported → Settings › System',
      '•Info Update available (2 new) → Settings › Update',
    ])
    expect(within(list).getByRole('link', { name: '→ Settings › Update' })).toHaveAttribute('href', '#/settings#update')
  })

  it('hides Attention when nothing needs a look, and never repeats the current focus', () => {
    const d = dashboardFixture()
    home({ ...d, issues: [], uncertainJobs: [] })
    expect(screen.queryByRole('region', { name: 'Attention' })).toBeNull()
    const steady: DashboardResponse = {
      ...d,
      paused: false,
      issues: [],
      uncertainJobs: [],
      approval: { ...d.approval, manifestSha256: SHA },
      standing: { ...d.standing, awaitingReview: 0, openFeedback: 0, nextPosts: [{ at: '2026-10-09T13:00:00Z', platform: 'x', episodeId: 'e' }] },
    }
    const j = journey({ dashboard: steady, update: updateInfo(), make: null, now })
    expect(j?.focus.title).toBe('Update the Pi')
    expect(attentionItems(steady, updateInfo(), j?.focus ?? null, now)).toEqual([])
  })

  it('flags token renewal failures and expiries within 7 days', () => {
    const d = dashboardFixture()
    d.statuses.currentlyAuthenticated.platforms.threads.expiresAt = '2026-10-11T12:00:00Z'
    d.statuses.currentlyAuthenticated.platforms.facebook.renewalFailed = true
    const items = attentionItems({ ...d, issues: [], uncertainJobs: [] }, null, null, now)
    expect(items.map((i) => [i.tone, i.text, i.to])).toEqual([
      ['bad', 'Facebook token renewal failed', 'home#platforms'],
      ['warn', 'Threads token expires in 3 days', 'home#platforms'],
    ])
    expect(platformRow(d, 'threads', now)).toMatchObject({ summary: 'Token renewal due', summaryTone: 'warn' })
    expect(platformRow(d, 'facebook', now)).toMatchObject({ summary: 'Token renewal failed', summaryTone: 'bad' })
  })

  it('shows one row per platform with three separate marks, never merged into one indicator', () => {
    home()
    const card = screen.getByRole('region', { name: 'Platforms' })
    const rows = within(card).getAllByTestId('platform-row')
    expect(rows).toHaveLength(7)
    const marks = (i: number) => within(rows[i] as HTMLElement).getAllByRole('img').map((m) => m.getAttribute('aria-label'))
    expect(marks(0)).toEqual(['Posting test: Passed', 'Authenticated: Unknown', 'Recurring: Disabled'])
    expect(marks(2)).toEqual(['Posting test: Not run', 'Authenticated: Authenticated', 'Recurring: Disabled'])
    // A passed test does not leak into the other marks.
    expect(marks(0).filter((m) => m?.endsWith('Passed'))).toHaveLength(1)
    expect(rows[0]).toHaveTextContent(/^Instagram.*Disabled/)
    expect(rows[1]).toHaveTextContent('Posting test: Not run')
    expect(within(card).getByText(/Recurring publishing overall: Not enabled · config paused · PAUSED sentinel present/)).toBeInTheDocument()
  })
})
