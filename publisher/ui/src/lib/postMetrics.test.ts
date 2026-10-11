import { describe, expect, it } from 'vitest'
import { accountRow, compact, metricsSummary } from './postMetrics'

describe('post metrics summary', () => {
  it('lists counts, watch time and answers in a fixed order', () => {
    const line = metricsSummary({
      checkpoint: '24h',
      fetchedAt: '2026-10-13T13:20:00Z',
      status: 'ok',
      values: { likes: 56, views: 12_345, reach: 9_800, ig_reels_avg_watch_time: 8400, 'answers.B': 30, 'answers.A': 12, total_interactions: 70 },
    })
    expect(line).toBe('12k views · 9.8k reached · 56 likes · 8.4 s avg watch · answers A 12 / B 30 (at 24h)')
  })

  it('explains reads that could not happen', () => {
    expect(metricsSummary(null)).toBeNull()
    expect(metricsSummary({ checkpoint: '1h', fetchedAt: '', status: 'authorization', values: {} })).toMatch(/insights permission/)
    expect(metricsSummary({ checkpoint: '1h', fetchedAt: '', status: 'unsupported', values: {} })).toMatch(/Buffer/)
    expect(metricsSummary({ checkpoint: '1h', fetchedAt: '', status: 'ok', values: {} })).toBe('No counts yet (at 1h)')
  })

  it('compacts large numbers', () => {
    expect([compact(999), compact(1000), compact(1500), compact(25_400), compact(2_000_000)]).toEqual(['999', '1k', '1.5k', '25k', '2M'])
  })

  it('formats an account row with follower change and missing numbers', () => {
    expect(accountRow({ platform: 'instagram', followers: 1200, followersChange: 35, days: 7, totals: { impressions: 6300, engagements: 315, engagement_rate: 0.05, profile_links_taps: 4 }, status: 'ok' })).toEqual({
      followers: '1.2k (+35)', impressions: '6.3k', engagements: '315', rate: '5.0%', clicks: '4', note: null,
    })
    expect(accountRow({ platform: 'facebook', followers: null, followersChange: null, days: 0, totals: {}, status: 'authorization' })).toMatchObject({
      followers: '—', rate: '—', note: 'Stats need the insights permission for this account',
    })
  })
})
