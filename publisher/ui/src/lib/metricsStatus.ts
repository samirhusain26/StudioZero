/** Plain words for the post stats controls (GET /api/metrics/status): never colour alone. */
import type { MetricsLastRun, MetricsPlatformRun, MetricsPlatformStatus, MetricsStatus } from '../api/types'
import type { Tone } from './labels'

/** How often the panel checks a pending read, and how long it waits before saying so. */
export const METRICS_POLL_MS = 4_000
export const METRICS_WAIT_MS = 5 * 60_000
export const BACKFILL_MAX = 93

export const YOUTUBE_KEY_COMMAND = 'sudo /opt/scalar-social/repo/publisher/deploy/enable-metrics.sh --youtube-key'

const PLATFORM_WORDS: Record<MetricsPlatformStatus, string> = {
  ok: 'read',
  'not-configured': 'not set up',
  authorization: 'access refused',
  rejected: "can't be read",
  error: 'read failed',
  unsupported: 'not readable by the Pi',
}

const PLATFORM_TONES: Record<MetricsPlatformStatus, Tone> = {
  ok: 'good',
  'not-configured': 'neutral',
  authorization: 'bad',
  rejected: 'warn',
  error: 'warn',
  unsupported: 'neutral',
}

/** One platform's status word in the last run, e.g. "read" or "can't be read (posted through Buffer)". */
export function platformWord(run: MetricsPlatformRun): string {
  const word = PLATFORM_WORDS[run.status] ?? run.status
  return run.status === 'rejected' && run.reason === 'buffer' ? `${word} (posted through Buffer)` : word
}

export function platformTone(run: MetricsPlatformRun): Tone {
  return PLATFORM_TONES[run.status] ?? 'neutral'
}

/** "3 posts, 1 account" read this run; null when nothing was read. */
export function readCounts(run: MetricsPlatformRun): string | null {
  const parts: string[] = []
  if (run.postsRead) parts.push(`${run.postsRead} post${run.postsRead === 1 ? '' : 's'}`)
  if (run.accountsRead) parts.push(`${run.accountsRead} account${run.accountsRead === 1 ? '' : 's'}`)
  return parts.length ? parts.join(', ') : null
}

const OUTCOME_WORDS: Record<MetricsLastRun['outcome'], string> = {
  ok: 'finished',
  'stats-off': 'skipped: hourly reads are off',
  'bad-request': 'the read request could not be used; ask again',
  error: 'failed; the Pi tries again next hour',
}

export function outcomeWords(outcome: MetricsLastRun['outcome']): string {
  return OUTCOME_WORDS[outcome] ?? outcome
}

export function outcomeTone(outcome: MetricsLastRun['outcome']): Tone {
  return outcome === 'ok' ? 'good' : outcome === 'stats-off' ? 'neutral' : 'warn'
}

/** "by the hourly timer" or "on request, also past 30 days". */
export function triggerWords(run: MetricsLastRun): string {
  const how = run.trigger === 'request' ? 'on request' : 'by the hourly timer'
  return run.backfill > 0 ? `${how}, also past ${run.backfill} day${run.backfill === 1 ? '' : 's'}` : how
}

/** Visible state after the fixed "Hourly reads" name (the button's state itself is aria-pressed). */
export function enabledLabel(status: MetricsStatus): string {
  return status.enabled ? 'On' : 'Off'
}

/** Platforms of the last run, in a stable order (the ones the Pi can read first, then the rest by name). */
const ORDER = ['instagram', 'facebook', 'threads', 'youtube', 'bluesky', 'x', 'tiktok']
export function platformRuns(run: MetricsLastRun): [string, MetricsPlatformRun][] {
  const rank = (p: string) => {
    const i = ORDER.indexOf(p)
    return i === -1 ? ORDER.length : i
  }
  return Object.entries(run.platforms).sort(([a], [b]) => rank(a) - rank(b) || a.localeCompare(b))
}

/** A backfill input value: a whole number of days 0–93, or null when it is not one. */
export function parseBackfill(text: string): number | null {
  const trimmed = text.trim()
  if (trimmed === '') return 0
  if (!/^\d+$/.test(trimmed)) return null
  const n = Number(trimmed)
  return n <= BACKFILL_MAX ? n : null
}
