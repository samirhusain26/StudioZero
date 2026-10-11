/**
 * Activity (docs/PI_UI_REDESIGN_PLAN.md §4.4): one timeline with single-select chips. "Posts" is the old
 * History (`/api/history`); the other chips are `/api/activity` kinds. Search and the ⋯ menu filters map
 * onto the same two queries.
 */
import type { ActivityEntry, ActivityKind, ActivityQuery, ActivitySeverity, HistoryQuery, HistoryStatus, Platform } from '../api/types'

export const ACTIVITY_TABS = [
  { id: 'all', label: 'All', kind: null },
  { id: 'posts', label: 'Posts', kind: null },
  { id: 'uploads', label: 'Uploads', kind: 'library' },
  { id: 'approvals', label: 'Approvals', kind: 'approval' },
  { id: 'system', label: 'System', kind: 'system' },
] as const satisfies readonly { id: string; label: string; kind: ActivityKind | null }[]

export type ActivityTab = (typeof ACTIVITY_TABS)[number]['id']

export function isActivityTab(id: string | null | undefined): id is ActivityTab {
  return ACTIVITY_TABS.some((t) => t.id === id)
}

export interface ActivityFilters {
  /** Search box: posts search on the Pi (episode, caption, permalink, job id); other tabs match loaded entries. */
  q: string
  platform: Platform | ''
  /** Timeline tabs only. */
  severity: ActivitySeverity | ''
  /** Posts only. */
  status: HistoryStatus | ''
  from: string
  to: string
}

export const NO_FILTERS: ActivityFilters = { q: '', platform: '', severity: '', status: '', from: '', to: '' }

export function feedQuery(tab: ActivityTab, f: ActivityFilters): ActivityQuery {
  const query: ActivityQuery = {}
  const kind = ACTIVITY_TABS.find((t) => t.id === tab)?.kind ?? null
  if (kind) query.kind = kind
  if (f.platform) query.platform = f.platform
  if (f.severity) query.severity = f.severity
  return query
}

export function postsQuery(f: ActivityFilters): HistoryQuery {
  const query: HistoryQuery = {}
  if (f.platform) query.platform = f.platform
  if (f.status) query.status = f.status
  if (f.q.trim()) query.q = f.q.trim()
  if (f.from) query.from = f.from
  if (f.to) query.to = f.to
  return query
}

/** Filters set in the ⋯ menu for this tab (the search box is visible and not counted). */
export function menuFilterCount(tab: ActivityTab, f: ActivityFilters): number {
  const posts = tab === 'posts'
  return [f.platform, posts ? f.status : f.severity, posts ? f.from : '', posts ? f.to : ''].filter(Boolean).length
}

/** Case-insensitive match of every search word against an entry's visible and id fields. */
export function matchesSearch(entry: ActivityEntry, q: string): boolean {
  const words = q.toLowerCase().split(/\s+/).filter(Boolean)
  if (!words.length) return true
  const hay = [entry.title, entry.detail, entry.platform, entry.jobId, entry.episode, entry.episodeId, entry.batchId, entry.game, entry.draftSha256, entry.manifestSha256]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return words.every((w) => hay.includes(w))
}
