import type { LibraryEpisode, Platform, QueueJob, ScheduleResponse } from '../api/types'
import { PLATFORMS } from '../api/types'
import { localDateKey } from './time'

/** Ledger states that mean the post will not go out (it does not cover its day). */
/** The autopilot refills the schedule once fewer than this many days remain (publisher/app/autopilot.py RUNWAY_DAYS). */
export const REFILL_DAYS = 7

const NOT_GOING_OUT = new Set<string>(['failed', 'expired', 'cancelled'])

/** How long one platform is covered: by the approved queue, then by approved videos not yet scheduled there. */
export interface PlatformRunway {
  platform: Platform
  /** Last local day with a live post in the approved queue, or null. */
  scheduledThrough: string | null
  /** Live posts from today on (local days). */
  postsLeft: number
  /** Approved videos eligible here, not posted or queued on this account (one per question). Null without the library. */
  spare: number | null
  /** scheduledThrough (or yesterday) plus one spare video a day, or null when there are none. */
  couldReach: string | null
}

export interface Runway {
  today: string
  platforms: PlatformRunway[]
  /** First local day on which an included platform has no queued post (the day after the earliest scheduledThrough). */
  firstGap: string | null
  firstGapPlatforms: Platform[]
  /** Last local day with any live post. */
  lastDay: string | null
  /** Last local day with a live post, per scheduling group (a Scalargame game, or the project id for others). */
  lastDayByGroup: Record<string, string>
}

export function addDays(dateKey: string, days: number): string {
  const date = new Date(`${dateKey}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

const live = (job: QueueJob) => job.kind === 'post' && !NOT_GOING_OUT.has(job.status)

/** Platforms the runway is about: the approved scope plus every channel that can be scheduled today. */
function includedPlatforms(schedule: ScheduleResponse): Platform[] {
  const wanted = new Set<Platform>(schedule.manifest?.scope ?? [])
  for (const c of schedule.channels) if (!c.blockedReason) wanted.add(c.platform)
  return PLATFORMS.filter((p) => wanted.has(p))
}

function spareFor(platform: Platform, episodes: readonly LibraryEpisode[], queued: ReadonlySet<string>): number {
  const questions = new Set<string>()
  for (const e of episodes) {
    if (e.status !== 'approved' || !e.currentApproval || !e.platforms[platform]?.eligible) continue
    if (queued.has(e.questionId)) continue
    if (e.postedOn.some((r) => r.platform === platform && !NOT_GOING_OUT.has(r.status))) continue
    questions.add(e.questionId)
  }
  return questions.size
}

export function computeRunway(schedule: ScheduleResponse, episodes: readonly LibraryEpisode[] | null, now = new Date()): Runway {
  const zone = schedule.displayTimezone
  const today = localDateKey(now.toISOString(), zone)
  const platforms = includedPlatforms(schedule).map((platform): PlatformRunway => {
    const jobs = schedule.jobs.filter((j) => j.platform === platform && live(j))
    const days = jobs.map((j) => localDateKey(j.slotUtc, zone)).sort()
    const scheduledThrough = days.at(-1) ?? null
    const postsLeft = days.filter((d) => d >= today).length
    const spare = episodes ? spareFor(platform, episodes, new Set(jobs.map((j) => j.questionId))) : null
    const base = scheduledThrough && scheduledThrough >= today ? scheduledThrough : addDays(today, -1)
    return { platform, scheduledThrough, postsLeft, spare, couldReach: spare ? addDays(base, spare) : null }
  })
  const ends = platforms.map((p) => (p.scheduledThrough && p.scheduledThrough >= today ? p.scheduledThrough : addDays(today, -1)))
  const earliest = [...ends].sort()[0] ?? null
  const liveDays = schedule.jobs.filter(live).map((j) => localDateKey(j.slotUtc, zone)).sort()
  const lastDayByGroup: Record<string, string> = {}
  for (const j of schedule.jobs.filter(live)) {
    const day = localDateKey(j.slotUtc, zone)
    if (j.game && day > (lastDayByGroup[j.game] ?? '')) lastDayByGroup[j.game] = day
  }
  return {
    lastDayByGroup,
    today,
    platforms,
    firstGap: earliest ? addDays(earliest, 1) : null,
    firstGapPlatforms: earliest ? platforms.filter((_, i) => ends[i] === earliest).map((p) => p.platform) : [],
    lastDay: liveDays.at(-1) ?? null,
  }
}

export interface CalendarDay {
  dateKey: string
  /** False for the leading/trailing days of the neighbouring months. */
  inMonth: boolean
  posts: QueueJob[]
}

export interface CalendarMonth {
  /** YYYY-MM */
  key: string
  weeks: CalendarDay[][]
}

/** Monday-first month grids from the month of `from` through the month of `to`, with each day's posts (not companions). */
export function calendarMonths(jobs: readonly QueueJob[], zone: string, from: string, to: string): CalendarMonth[] {
  const byDay = new Map<string, QueueJob[]>()
  for (const job of [...jobs].sort((a, b) => a.slotUtc.localeCompare(b.slotUtc))) {
    if (job.kind !== 'post') continue
    const key = localDateKey(job.slotUtc, zone)
    byDay.set(key, [...(byDay.get(key) ?? []), job])
  }
  const months: CalendarMonth[] = []
  let first = `${from.slice(0, 7)}-01`
  const last = to.slice(0, 7)
  while (first.slice(0, 7) <= last && months.length < 12) {
    const month = first.slice(0, 7)
    const weekday = (new Date(`${first}T00:00:00Z`).getUTCDay() + 6) % 7
    let day = addDays(first, -weekday)
    const weeks: CalendarDay[][] = []
    while (day.slice(0, 7) <= month) {
      const week: CalendarDay[] = []
      for (let i = 0; i < 7; i++) {
        week.push({ dateKey: day, inMonth: day.slice(0, 7) === month, posts: byDay.get(day) ?? [] })
        day = addDays(day, 1)
      }
      weeks.push(week)
    }
    months.push({ key: month, weeks })
    const next = new Date(`${first}T00:00:00Z`)
    next.setUTCMonth(next.getUTCMonth() + 1)
    first = next.toISOString().slice(0, 10)
  }
  return months
}
