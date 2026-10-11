/** Pure helpers for the Activity feed: severity labels, day grouping and page merging. */
import type { ActivityEntry, ActivityKind, ActivitySeverity } from '../api/types'
import type { Tone } from './labels'
import { localDateKey } from './time'

export const ACTIVITY_SEVERITY: Record<ActivitySeverity, { label: string; tone: Tone }> = {
  error: { label: 'Error', tone: 'bad' },
  warning: { label: 'Warning', tone: 'warn' },
  success: { label: 'Success', tone: 'good' },
  info: { label: 'Info', tone: 'info' },
}

export const ACTIVITY_KIND_LABELS: Record<ActivityKind, string> = {
  job: 'Posts and replies',
  approval: 'Schedules and approvals',
  library: 'Library',
  system: 'System and timers',
}

export interface ActivityDay {
  dateKey: string
  entries: ActivityEntry[]
}

/** Group newest-first entries by their local calendar day, keeping order. */
export function groupByDay(entries: readonly ActivityEntry[], zone: string): ActivityDay[] {
  const days: ActivityDay[] = []
  for (const entry of entries) {
    const key = localDateKey(entry.at, zone)
    const last = days[days.length - 1]
    if (last && last.dateKey === key) last.entries.push(entry)
    else days.push({ dateKey: key, entries: [entry] })
  }
  return days
}

/**
 * A refreshed first page plus older pages loaded earlier: keep the fresh head, then every older
 * entry strictly below the head's oldest id (ids are the server's sort keys), without duplicates.
 */
export function mergeHead(head: readonly ActivityEntry[], older: readonly ActivityEntry[], headComplete: boolean): ActivityEntry[] {
  const last = head[head.length - 1]
  if (headComplete || !last) return [...head]
  const floor = last.id
  const seen = new Set(head.map((e) => e.id))
  return [...head, ...older.filter((e) => e.id < floor && !seen.has(e.id))]
}
