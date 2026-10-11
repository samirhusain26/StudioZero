/** Pure model for the schedule generator form. It starts empty: no cadence or zone is invented. */
import type { DraftEdit, DraftJob, OrderingRule, Platform, PlatformScheduleInput, ScheduleInputs, Weekday } from '../api/types'
import { PLATFORMS } from '../api/types'
import { isValidTimeZone, localDateKey } from './time'

export interface PlatformForm {
  include: boolean
  weekdays: Weekday[]
  times: string[]
  maxPerDay: string
  minGapHours: string
}

export interface ScheduleForm {
  timezone: string
  startDate: string
  endDate: string
  platforms: Record<Platform, PlatformForm>
  staggerMinutes: string
  ordering: OrderingRule
  firstComment: boolean
  answerReply: boolean
}

export const WEEKDAYS: { value: Weekday; short: string; long: string }[] = [
  { value: 0, short: 'Mon', long: 'Monday' },
  { value: 1, short: 'Tue', long: 'Tuesday' },
  { value: 2, short: 'Wed', long: 'Wednesday' },
  { value: 3, short: 'Thu', long: 'Thursday' },
  { value: 4, short: 'Fri', long: 'Friday' },
  { value: 5, short: 'Sat', long: 'Saturday' },
  { value: 6, short: 'Sun', long: 'Sunday' },
]

/** One-tap suggestion only; never pre-filled. */
export const SUGGESTED_TIMEZONE = 'America/New_York'

/**
 * The recommended cadence, applied only when the owner taps it: one video per platform per day, every day,
 * at a time spread across the day (each on a 15-minute runner tick, clear of the 04:30 token refreshes).
 * Rationale and sources: publisher/docs/SCHEDULE.md.
 */
export const RECOMMENDED_TIMES: Record<Platform, string> = {
  threads: '09:00',
  x: '09:30',
  bluesky: '10:30',
  facebook: '12:15',
  youtube: '16:00',
  instagram: '18:00',
  tiktok: '19:00',
}
/** About one library's runway at one post per platform per day. */
export const RECOMMENDED_DAYS = 21

function addDays(dateKey: string, days: number): string {
  const date = new Date(`${dateKey}T00:00:00Z`)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

/** The recommended form, starting the day after `today` (YYYY-MM-DD in the suggested zone); blocked platforms stay out. */
export function recommendedScheduleForm(today: string, blocked: ReadonlySet<Platform>): ScheduleForm {
  const form = emptyScheduleForm()
  form.timezone = SUGGESTED_TIMEZONE
  form.startDate = addDays(today, 1)
  form.endDate = addDays(today, RECOMMENDED_DAYS)
  for (const p of PLATFORMS) {
    if (blocked.has(p)) continue
    form.platforms[p] = { include: true, weekdays: [0, 1, 2, 3, 4, 5, 6], times: [RECOMMENDED_TIMES[p]], maxPerDay: '1', minGapHours: '2' }
  }
  form.staggerMinutes = '0'
  form.firstComment = true
  form.answerReply = true
  return form
}

/**
 * Schedule › New draft, preset first: the recommended form with the owner's start date and timezone (the two
 * visible fields). Only built when Generate or Customize is tapped; until then nothing is form state.
 * With the default start (tomorrow) it equals recommendedScheduleForm exactly, so the draft hash is the same.
 */
export function presetForm(today: string, blocked: ReadonlySet<Platform>, overrides: { startDate?: string; timezone?: string } = {}): ScheduleForm {
  const form = recommendedScheduleForm(today, blocked)
  const zone = overrides.timezone?.trim()
  if (zone) form.timezone = zone
  if (overrides.startDate && DATE.test(overrides.startDate)) {
    form.startDate = overrides.startDate
    form.endDate = addDays(overrides.startDate, RECOMMENDED_DAYS - 1)
  }
  return form
}

/** The default proposal shown before anything is tapped: tomorrow in the suggested zone. */
export function presetStartDate(today: string): string {
  return addDays(today, 1)
}

function emptyPlatform(): PlatformForm {
  return { include: false, weekdays: [], times: [], maxPerDay: '', minGapHours: '' }
}

export function emptyScheduleForm(): ScheduleForm {
  const platforms = {} as Record<Platform, PlatformForm>
  for (const p of PLATFORMS) platforms[p] = emptyPlatform()
  return {
    timezone: '',
    startDate: '',
    endDate: '',
    platforms,
    staggerMinutes: '',
    ordering: 'game-round-robin',
    firstComment: false,
    answerReply: false,
  }
}

const DATE = /^\d{4}-\d{2}-\d{2}$/
const TIME = /^([01]\d|2[0-3]):[0-5]\d$/

export type InputsResult = { ok: true; inputs: ScheduleInputs } | { ok: false; errors: string[] }

export function buildScheduleInputs(form: ScheduleForm): InputsResult {
  const errors: string[] = []
  const zone = form.timezone.trim()
  if (!zone) errors.push('Enter a timezone (IANA name such as America/New_York).')
  else if (!isValidTimeZone(zone)) errors.push(`“${zone}” is not a timezone this browser recognises.`)
  if (!DATE.test(form.startDate)) errors.push('Choose a start date.')
  if (!DATE.test(form.endDate)) errors.push('Choose an end date.')
  if (DATE.test(form.startDate) && DATE.test(form.endDate) && form.endDate < form.startDate) errors.push('The end date is before the start date.')

  const platforms: Partial<Record<Platform, PlatformScheduleInput>> = {}
  const minGapHours: Partial<Record<Platform, number>> = {}
  const included = PLATFORMS.filter((p) => form.platforms[p].include)
  if (included.length === 0) errors.push('Include at least one platform.')
  for (const p of included) {
    const f = form.platforms[p]
    if (f.weekdays.length === 0) errors.push(`${p}: choose at least one weekday.`)
    if (f.times.length === 0) errors.push(`${p}: add at least one time.`)
    if (f.times.some((t) => !TIME.test(t))) errors.push(`${p}: times must be HH:MM (24-hour).`)
    if (new Set(f.times).size !== f.times.length) errors.push(`${p}: duplicate times.`)
    const max = Number(f.maxPerDay)
    if (!f.maxPerDay.trim() || !Number.isInteger(max) || max < 1) errors.push(`${p}: max posts per day must be a whole number ≥ 1.`)
    const gap = Number(f.minGapHours)
    if (!f.minGapHours.trim() || !Number.isFinite(gap) || gap < 0) errors.push(`${p}: minimum gap must be a number of hours ≥ 0.`)
    platforms[p] = {
      include: true,
      weekdays: [...f.weekdays].sort((a, b) => a - b),
      times: [...f.times].sort(),
      maxPerDay: max,
    }
    minGapHours[p] = gap
  }
  const stagger = Number(form.staggerMinutes)
  if (!form.staggerMinutes.trim() || !Number.isInteger(stagger) || stagger < 0) errors.push('Stagger must be a whole number of minutes ≥ 0 (0 = none).')

  if (errors.length) return { ok: false, errors }
  return {
    ok: true,
    inputs: {
      timezone: zone,
      startDate: form.startDate,
      endDate: form.endDate,
      platforms,
      minGapHours,
      staggerMinutes: stagger,
      ordering: form.ordering,
      companions: { firstComment: form.firstComment, answerReply: form.answerReply },
      edits: {},
    },
  }
}

/** New inputs with one job edit merged in (any edit produces a new draft hash). */
export function withEdit(inputs: ScheduleInputs, key: string, edit: DraftEdit): ScheduleInputs {
  return { ...inputs, edits: { ...inputs.edits, [key]: edit } }
}

export interface JobGroup {
  job: DraftJob
  companions: DraftJob[]
}

export interface DayGroup {
  dateKey: string
  items: JobGroup[]
}

const platformIndex = (p: Platform) => PLATFORMS.indexOf(p)

function byTime(a: DraftJob, b: DraftJob): number {
  return a.slotUtc < b.slotUtc ? -1 : a.slotUtc > b.slotUtc ? 1 : platformIndex(a.platform) - platformIndex(b.platform)
}

/** Group jobs by local day in `zone`; companions nest under their parent. */
export function groupDraftJobs(jobs: readonly DraftJob[], zone: string): DayGroup[] {
  const keys = new Set(jobs.map((j) => j.key))
  const parents = jobs.filter((j) => !j.parentKey || !keys.has(j.parentKey)).sort(byTime)
  const children = new Map<string, DraftJob[]>()
  for (const j of jobs) {
    if (j.parentKey && keys.has(j.parentKey)) {
      const list = children.get(j.parentKey) ?? []
      list.push(j)
      children.set(j.parentKey, list)
    }
  }
  const days = new Map<string, JobGroup[]>()
  for (const job of parents) {
    const day = localDateKey(job.slotUtc, zone)
    const list = days.get(day) ?? []
    list.push({ job, companions: (children.get(job.key) ?? []).sort(byTime) })
    days.set(day, list)
  }
  return [...days.entries()].sort(([a], [b]) => (a < b ? -1 : 1)).map(([dateKey, items]) => ({ dateKey, items }))
}

export function fillSummary(draft: { summary: { requested: number; filled: number } }): string {
  const { requested, filled } = draft.summary
  return `${filled} of ${requested} requested slot${requested === 1 ? '' : 's'} fillable`
}
