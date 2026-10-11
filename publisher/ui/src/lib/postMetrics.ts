/** One-line wording for a post's newest platform read (publisher/app/metrics.py). */
import type { AccountStats, PostMetrics } from '../api/types'

/** Shown in this order; anything else stays in the data and the feedback export only. */
const COUNTS: [string, string][] = [
  ['views', 'views'],
  ['blue_reels_play_count', 'plays'],
  ['reach', 'reached'],
  ['post_impressions_unique', 'reached'],
  ['likes', 'likes'],
  ['comments', 'comments'],
  ['replies', 'replies'],
  ['shares', 'shares'],
  ['saved', 'saves'],
  ['reposts', 'reposts'],
  ['quotes', 'quotes'],
]

const STATUS: Record<string, string> = {
  authorization: 'Stats need the insights permission for this account',
  not_configured: 'Stats are not set up for this platform yet',
  unsupported: 'This platform gives no stats to the Pi (check it in Buffer)',
  gone: 'The platform no longer finds this post',
  rejected: 'The platform refused the stats request',
  uncertain: 'Stats read failed; the Pi retries next hour',
  rate_limit: 'Stats read was rate-limited; the Pi retries next hour',
}

export function compact(n: number): string {
  if (n < 1000) return String(Math.round(n * 10) / 10)
  if (n < 1_000_000) return `${(n / 1000).toFixed(n < 10_000 ? 1 : 0).replace(/\.0$/, '')}k`
  return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`
}

export function metricsSummary(m: PostMetrics | null | undefined): string | null {
  if (!m) return null
  if (m.status !== 'ok') return STATUS[m.status] ?? 'Stats unavailable'
  const v = m.values
  const parts: string[] = []
  const used = new Set<string>()
  for (const [key, label] of COUNTS) {
    if (typeof v[key] === 'number' && !used.has(label)) {
      parts.push(`${compact(v[key])} ${label}`)
      used.add(label)
    }
  }
  // Instagram reports average watch time in milliseconds.
  if (typeof v.ig_reels_avg_watch_time === 'number') parts.push(`${(v.ig_reels_avg_watch_time / 1000).toFixed(1)} s avg watch`)
  const answers = ['A', 'B', 'C', 'D'].filter((k) => typeof v[`answers.${k}`] === 'number').map((k) => `${k} ${v[`answers.${k}`]}`)
  if (answers.length) parts.push(`answers ${answers.join(' / ')}`)
  return `${parts.length ? parts.join(' · ') : 'No counts yet'} (at ${m.checkpoint})`
}

const ACCOUNT_STATUS: Record<string, string> = {
  ...STATUS,
  unsupported: 'No account stats for this platform',
}

/** Table cells for one account's last 7 days; '—' where the platform gives no number. */
export function accountRow(a: AccountStats): { followers: string; impressions: string; engagements: string; rate: string; clicks: string; note: string | null } {
  const t = a.totals
  const n = (v: number | undefined) => (typeof v === 'number' ? compact(v) : '—')
  const change = a.followersChange === null ? '' : ` (${a.followersChange >= 0 ? '+' : '−'}${compact(Math.abs(a.followersChange))})`
  const clicks = t.clicks ?? t.profile_links_taps
  return {
    followers: a.followers === null ? '—' : `${compact(a.followers)}${change}`,
    impressions: n(t.impressions),
    engagements: n(t.engagements),
    rate: typeof t.engagement_rate === 'number' ? `${(t.engagement_rate * 100).toFixed(1)}%` : '—',
    clicks: n(clicks),
    note: a.status === 'ok' ? null : (ACCOUNT_STATUS[a.status] ?? 'Some stats could not be read'),
  }
}
