import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { EpisodeFunnel, FunnelPlatform } from '../../api/types'
import { FunnelTable } from './FunnelTable'

const none: FunnelPlatform = { status: null, views: null, engaged: null, answered: null, avgWatchSeconds: null, followsThatDay: null, followsSource: null }

const funnelRow = (over: Partial<EpisodeFunnel> = {}): EpisodeFunnel => ({
  episode: 'scalar-clues-001',
  labels: null,
  publishedDates: ['2026-10-05'],
  views: 1530,
  engaged: 84,
  answered: 21,
  avgWatchSeconds: 8.25,
  followsThatDay: 6,
  counted: { views: ['instagram', 'youtube'], engaged: ['instagram'], answered: ['instagram'], avgWatchSeconds: ['instagram'], followsThatDay: ['instagram', 'youtube'] },
  platforms: {
    instagram: { status: 'ok', views: 1500, engaged: 84, answered: 21, avgWatchSeconds: 8.25, followsThatDay: 5, followsSource: 'day-metric' },
    youtube: { status: 'ok', views: 30, engaged: null, answered: null, avgWatchSeconds: null, followsThatDay: 1, followsSource: 'follower-change' },
    x: { ...none, status: 'pending' },
    tiktok: { ...none, status: 'ok', views: 120 },
  },
  ...over,
})

describe('Per-video funnel', () => {
  it('is a real table: one row per episode, columns in funnel order', () => {
    render(<FunnelTable funnel={[funnelRow()]} />)
    const table = screen.getByRole('table', { name: /for each posted episode/ })
    const head = within(table).getAllByRole('columnheader').slice(0, 6).map((h) => h.textContent)
    expect(head).toEqual(['Episode', 'Views', 'Avg watch', 'Engaged', 'Answered', 'Follows that day'])
    const row = within(table).getByRole('rowheader', { name: /scalar-clues-001/ }).closest('tr')
    expect(row).toHaveTextContent('scalar-clues-001Posted 2026-10-051.5k8.3 s84216')
  })

  it('shows a dash with "no data" words for missing numbers, never zero', () => {
    render(
      <FunnelTable
        funnel={[funnelRow({ episode: 'tectonic-clues-004', views: null, engaged: null, answered: null, avgWatchSeconds: null, followsThatDay: null, platforms: {}, counted: { views: [], engaged: [], answered: [], avgWatchSeconds: [], followsThatDay: [] } })]}
      />,
    )
    const row = screen.getByRole('rowheader', { name: /tectonic-clues-004/ }).closest('tr') as HTMLElement
    const cells = within(row).getAllByRole('cell')
    expect(cells).toHaveLength(5)
    for (const cell of cells) expect(cell).toHaveTextContent('—no data')
    expect(within(row).queryByText('0')).not.toBeInTheDocument()
  })

  it('breaks a row down by platform behind a disclosure, with the follows source', async () => {
    const user = userEvent.setup()
    render(<FunnelTable funnel={[funnelRow()]} />)
    const summary = screen.getByText('By platform: scalar-clues-001')
    const details = summary.closest('details') as HTMLDetailsElement
    expect(details.open).toBe(false)
    await user.click(summary)
    expect(details.open).toBe(true)
    const inner = within(details).getByRole('table', { name: 'scalar-clues-001 by platform' })
    expect(within(inner).getByRole('rowheader', { name: 'Instagram' }).closest('tr')).toHaveTextContent('Instagramread1.5k8.3 s84215 (day follows)')
    expect(within(inner).getByRole('rowheader', { name: 'YouTube' }).closest('tr')).toHaveTextContent('YouTuberead30—no data—no data—no data1 (follower change)')
    expect(within(inner).getByRole('rowheader', { name: 'X' }).closest('tr')).toHaveTextContent("waiting for Buffer's daily numbers")
    expect(within(inner).getByRole('rowheader', { name: 'TikTok' }).closest('tr')).toHaveTextContent('read via Buffer (daily)120')
    expect(within(details).getByText(/^Totals add up views: Instagram, YouTube/)).toBeInTheDocument()
  })

  it('says follows are account-level, not attributed, and that X and TikTok come from Buffer daily', () => {
    render(<FunnelTable funnel={[]} />)
    expect(screen.getByText(/No per-video stats yet/)).toBeInTheDocument()
    expect(screen.getByText(/account-level for that day, not attributed to the video/)).toBeInTheDocument()
    expect(screen.getByText(/X and TikTok come from Buffer, which refreshes its numbers once a day/)).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
})
