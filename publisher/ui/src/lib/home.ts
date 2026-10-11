/**
 * Home (docs/PI_UI_REDESIGN_PLAN.md §4.1) beyond the loop: the Attention list and one row per platform.
 * Pure functions of the dashboard payload, so Home and its tests read the same facts.
 */
import type { DashboardResponse, Platform, TriState, UpdateInfo } from '../api/types'
import { PLATFORMS } from '../api/types'
import { platformName, shortHash } from './format'
import type { Focus } from './journey'
import { triTone, type Tone } from './labels'
import { updateAvailable } from './update'

export const TOKEN_WARN_DAYS = 7
const DAY_MS = 86_400_000

export interface AttentionItem {
  id: string
  tone: Extract<Tone, 'bad' | 'warn' | 'info'>
  text: string
  /** Route path (without `#/`) where it is dealt with, and that place's name. */
  to: string
  where: string
}

function daysUntil(iso: string | null, now: Date): number | null {
  if (!iso) return null
  const at = Date.parse(iso)
  return Number.isNaN(at) ? null : Math.ceil((at - now.getTime()) / DAY_MS)
}

/**
 * Things that need a look, worst first. Empty when all is well (Home then hides the list). The item for
 * the loop's current focus is left out: the loop card already says it.
 */
export function attentionItems(data: DashboardResponse, update: UpdateInfo | null, focus: Focus | null, now: Date): AttentionItem[] {
  const items: AttentionItem[] = []
  const uncertain = new Set(data.uncertainJobs.map((j) => j.jobId))
  for (const job of data.uncertainJobs) {
    items.push({
      id: `uncertain:${job.jobId}`,
      tone: 'warn',
      text: `${platformName(job.platform)} job ${shortHash(job.jobId, 8)} is uncertain and needs reconciling (owner command)`,
      to: 'settings#system',
      where: 'Settings › System',
    })
  }
  for (const issue of data.issues) {
    if (issue.severity === 'info' || (issue.jobId && uncertain.has(issue.jobId))) continue
    items.push({
      id: `issue:${issue.id}`,
      tone: issue.severity === 'error' ? 'bad' : 'warn',
      text: `${issue.platform ? `${platformName(issue.platform)}: ` : ''}${issue.title}`,
      to: issue.jobId ? 'activity' : 'settings#system',
      where: issue.jobId ? 'Activity' : 'Settings › System',
    })
  }
  for (const p of PLATFORMS) {
    const auth = data.statuses.currentlyAuthenticated.platforms[p]
    const days = daysUntil(auth.expiresAt, now)
    if (auth.renewalFailed) {
      items.push({ id: `renewal:${p}`, tone: 'bad', text: `${platformName(p)} token renewal failed`, to: 'home#platforms', where: 'Platforms' })
    } else if (days !== null && days <= TOKEN_WARN_DAYS) {
      items.push({
        id: `expiry:${p}`,
        tone: days <= 0 ? 'bad' : 'warn',
        text: days <= 0 ? `${platformName(p)} token has expired` : `${platformName(p)} token expires in ${days} day${days === 1 ? '' : 's'}`,
        to: 'home#platforms',
        where: 'Platforms',
      })
    }
  }
  if (updateAvailable(update) && focus?.action?.to !== 'settings#update') {
    const behind = update?.status.check?.behind ?? 0
    items.push({ id: 'update', tone: 'info', text: `Update available (${behind} new)`, to: 'settings#update', where: 'Settings › Update' })
  }
  const rank: Record<AttentionItem['tone'], number> = { bad: 0, warn: 1, info: 2 }
  return items.sort((a, b) => rank[a.tone] - rank[b.tone])
}

export interface PlatformMark {
  name: 'Posting test' | 'Authenticated' | 'Recurring'
  state: TriState
  tone: Tone
  label: string
}

export interface PlatformRow {
  platform: Platform
  name: string
  /** The three separate facts, never merged: posting test passed · currently authenticated · recurring enabled. */
  marks: [PlatformMark, PlatformMark, PlatformMark]
  /** One short summary: what matters most for this platform right now. */
  summary: string
  summaryTone: Tone
}

export function platformRow(data: DashboardResponse, p: Platform, now: Date): PlatformRow {
  const posting = data.statuses.postingTestPassed.platforms[p]
  const auth = data.statuses.currentlyAuthenticated.platforms[p]
  const recurring = data.statuses.recurringEnabled.platforms[p]
  const authTone: Tone = auth.renewalFailed ? 'bad' : triTone(auth.state)
  const marks: PlatformRow['marks'] = [
    { name: 'Posting test', state: posting.state, tone: triTone(posting.state), label: posting.label },
    { name: 'Authenticated', state: auth.state, tone: authTone, label: auth.renewalFailed && !/renew/i.test(auth.label) ? `${auth.label} (renewal failed)` : auth.label },
    { name: 'Recurring', state: recurring.state, tone: triTone(recurring.state), label: recurring.label },
  ]
  const days = daysUntil(auth.expiresAt, now)
  let summary = recurring.label
  let summaryTone: Tone = triTone(recurring.state)
  if (auth.renewalFailed) [summary, summaryTone] = ['Token renewal failed', 'bad']
  else if (days !== null && days <= TOKEN_WARN_DAYS) [summary, summaryTone] = [days <= 0 ? 'Token expired' : 'Token renewal due', days <= 0 ? 'bad' : 'warn']
  else if (recurring.state !== 'yes' && auth.state === 'no') [summary, summaryTone] = [auth.label, 'bad']
  else if (recurring.state !== 'yes' && posting.state === 'no') [summary, summaryTone] = [`Posting test: ${posting.label}`, triTone(posting.state)]
  return { platform: p, name: platformName(p), marks, summary, summaryTone }
}

export function platformRows(data: DashboardResponse, now: Date): PlatformRow[] {
  return PLATFORMS.map((p) => platformRow(data, p, now))
}
