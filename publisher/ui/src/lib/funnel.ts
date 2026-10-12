/** Cell text for the per-video funnel (NextBatchInfo.funnel). null always means "no data", never zero. */
import type { EpisodeFunnel, FollowsSource, FunnelCounted, FunnelLabels, FunnelPlatform } from '../api/types'
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

export const GROUP_KEYS = [
  { id: 'project', label: 'Project' },
  { id: 'engine', label: 'Engine' },
  { id: 'format', label: 'Format' },
  { id: 'renderer', label: 'Renderer' },
] as const
export type GroupKey = (typeof GROUP_KEYS)[number]['id']

export interface FunnelGroup {
  key: string
  videos: number
  /** Sums over the videos that have the number; null when none has it (never zero for "no data"). */
  views: number | null
  engaged: number | null
  answered: number | null
  /** engaged ÷ views over videos with both, as a percentage with one decimal; null without both. */
  engagedRate: number | null
}

function groupLabel(labels: FunnelLabels | null, key: GroupKey): string {
  if (!labels) return 'Not in the library'
  if (key === 'renderer') return labels.renderer === 'web' ? 'Browser export' : labels.renderer === 'render.sh' ? 'Mac (render.sh)' : 'Not recorded'
  if (key === 'engine') return labels.route ? `${labels.engine} · ${labels.route}` : labels.engine
  return labels[key] ?? '—'
}

const add = (a: number | null, b: number | null) => (b === null ? a : (a ?? 0) + b)

/** Learn: per-video funnel rows added up by project, engine, format or renderer (largest view count first). */
export function groupFunnel(rows: EpisodeFunnel[], key: GroupKey): FunnelGroup[] {
  const groups = new Map<string, FunnelGroup & { both: [number, number] }>()
  for (const row of rows) {
    const name = groupLabel(row.labels, key)
    const g = groups.get(name) ?? { key: name, videos: 0, views: null, engaged: null, answered: null, engagedRate: null, both: [0, 0] }
    g.videos++
    g.views = add(g.views, row.views)
    g.engaged = add(g.engaged, row.engaged)
    g.answered = add(g.answered, row.answered)
    if (row.views !== null && row.engaged !== null) g.both = [g.both[0] + row.engaged, g.both[1] + row.views]
    groups.set(name, g)
  }
  return [...groups.values()]
    .map(({ both, ...g }) => ({ ...g, engagedRate: both[1] > 0 ? Math.round((both[0] / both[1]) * 1000) / 10 : null }))
    .sort((a, b) => (b.views ?? -1) - (a.views ?? -1) || a.key.localeCompare(b.key))
}
