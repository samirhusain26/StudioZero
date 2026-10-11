/** Cell text for the per-video funnel (NextBatchInfo.funnel). null always means "no data", never zero. */
import type { EpisodeFunnel, FollowsSource, FunnelCounted, FunnelPlatform } from '../api/types'
import { platformName } from './format'
import { compact } from './postMetrics'

/** Platforms read through Buffer, which refreshes its numbers once a day (so they lag up to a day). */
export const VIA_BUFFER = ['x', 'tiktok'] as const

export function countText(n: number | null): string | null {
  return n === null ? null : compact(n)
}

export function watchText(seconds: number | null): string | null {
  return seconds === null ? null : `${seconds.toFixed(1)} s`
}

const FOLLOWS_SOURCE: Record<FollowsSource, string> = {
  'day-metric': 'day follows',
  'follower-change': 'follower change',
}

export function followsSourceText(source: FollowsSource | null): string | null {
  return source ? FOLLOWS_SOURCE[source] : null
}

const READ_STATUS: Record<string, string> = {
  ok: 'read',
  authorization: 'access refused',
  not_configured: 'not set up',
  'not-configured': 'not set up',
  unsupported: 'not readable by the Pi',
  gone: 'post gone',
  rejected: "can't be read",
  uncertain: 'read failed, retrying',
  error: 'read failed, retrying',
  rate_limit: 'rate-limited, retrying',
  pending: "waiting for Buffer's daily numbers",
}

/** The newest stored read of this platform's post, in words ("via Buffer, daily" for X and TikTok). */
export function platformReadText(platform: string, p: FunnelPlatform): string {
  const words = p.status === null ? 'not read yet' : (READ_STATUS[p.status] ?? p.status)
  return (VIA_BUFFER as readonly string[]).includes(platform) && p.status === 'ok' ? `${words} via Buffer (daily)` : words
}

/** Platforms of one row, by display name. */
export function funnelPlatforms(row: EpisodeFunnel): [string, FunnelPlatform][] {
  return Object.entries(row.platforms).sort(([a], [b]) => platformName(a).localeCompare(platformName(b)))
}

const COUNTED_LABELS: [keyof FunnelCounted, string][] = [
  ['views', 'views'],
  ['avgWatchSeconds', 'avg watch'],
  ['engaged', 'engaged'],
  ['answered', 'answered'],
  ['followsThatDay', 'follows'],
]

/** "views: Instagram, YouTube · avg watch: Instagram" — which platforms went into each total. */
export function countedText(counted: FunnelCounted): string | null {
  const parts = COUNTED_LABELS.filter(([key]) => counted[key].length > 0).map(
    ([key, label]) => `${label}: ${counted[key].map(platformName).join(', ')}`,
  )
  return parts.length ? parts.join(' · ') : null
}
