/**
 * The loop (docs/PI_UI_REDESIGN_PLAN.md §0): Make → Upload → Review → Schedule → Post → Learn → Make…
 * The single source of step state for Home, the step line under every title and the empty states.
 * Pure: a function of the dashboard payload, the last update check and the browser-local Make checklist.
 *
 * The focus (the one current step and its action), first match wins — content flow before housekeeping:
 *   1. Episodes are awaiting review            → Review. Nothing can be scheduled before approval.
 *   2. The last batch still misses files        → Upload: finish it (files on the Pi are skipped).
 *   3. No Mac batch was ever imported           → Make the first batch (or Upload once its checklist is finalized).
 *   4. No approved schedule exists              → Schedule.
 *   5. The last batch is ≥ 6 weeks old, no post
 *      is scheduled in the next 14 days, or the
 *      next batch was started in this browser   → Make the next batch (or Upload once finalized).
 *   6. Publishing is paused                     → Post, blocked: resuming is the owner's command.
 *   7. The last update check found new code     → Settings › Update (kept with Post: it keeps posting healthy).
 *   8. Open feedback, or a retro newer than
 *      the last brief                           → Learn: carry it into the next batch.
 *   9. Otherwise                                → Post: nothing needs the owner.
 */
import type { DashboardResponse, Standing, UpdateInfo } from '../api/types'
import { makeComplete, type MakeProgress } from './makeChecklist'
import { formatDayHeading } from './time'
import { updateAvailable } from './update'

export const STALE_BATCH_DAYS = 42
export const RUNWAY_DAYS = 14
const DAY_MS = 86_400_000

export const STEPS = [
  { id: 'make', n: 1, label: 'Make', mac: true },
  { id: 'upload', n: 2, label: 'Upload', mac: false },
  { id: 'review', n: 3, label: 'Review', mac: false },
  { id: 'schedule', n: 4, label: 'Schedule', mac: false },
  { id: 'post', n: 5, label: 'Post', mac: false },
  { id: 'learn', n: 6, label: 'Learn', mac: false },
] as const

export type StepId = (typeof STEPS)[number]['id']
export type StepState = 'todo' | 'current' | 'done' | 'blocked'

export interface StepAction {
  label: string
  /** Route path without `#/`, e.g. `studio/make` or `settings#activation`. */
  to: string
}

export interface Focus {
  step: StepId
  title: string
  detail: string
  /** The one primary action, or null when nothing needs doing. */
  action: StepAction | null
}

export interface JourneyStep {
  id: StepId
  n: number
  label: string
  mac: boolean
  state: StepState
  /** One line: the step's fact (done), why it is blocked and who unblocks it, or what is waiting. */
  fact: string
}

export interface Journey {
  steps: JourneyStep[]
  focus: Focus
  current: JourneyStep
}

export interface FocusInput {
  standing: Standing | null | undefined
  hasApprovedSchedule: boolean
  paused: boolean
  update: UpdateInfo | null
  make: MakeProgress | null
  now: Date
}

const plural = (n: number, word: string, many = `${word}s`) => `${n} ${n === 1 ? word : many}`

function runway(standing: Standing, t: number): boolean {
  return standing.nextPosts.some((p) => {
    const at = Date.parse(p.at)
    return !Number.isNaN(at) && at - t <= RUNWAY_DAYS * DAY_MS
  })
}

/** The approved schedule ends within RUNWAY_DAYS: time to make the next batch (it must be approved by nextBatchBy). */
function runningOut(standing: Standing, t: number): boolean {
  const end = standing.contentThrough ? Date.parse(`${standing.contentThrough}T23:59:59Z`) : NaN
  return !Number.isNaN(end) && end - t <= RUNWAY_DAYS * DAY_MS
}

function stale(standing: Standing, t: number): boolean {
  const imported = standing.lastBatch ? Date.parse(standing.lastBatch.importedAt) : NaN
  return !Number.isNaN(imported) && t - imported >= STALE_BATCH_DAYS * DAY_MS
}

function retroWaiting(standing: Standing): boolean {
  return Boolean(standing.lastRetroAt && (!standing.lastBriefAt || standing.lastRetroAt > standing.lastBriefAt))
}

function makeFocus(standing: Standing | null | undefined, make: MakeProgress | null, title: string, detail: string): Focus {
  const id = standing?.nextBatchId ?? make?.batchId ?? null
  if (id && makeComplete(make)) {
    return {
      step: 'upload',
      title: `Finalize and upload ${id}`,
      detail: `The Mac checklist is done. Once Claude has written READY_FOR_UPLOAD, drop library/${id}/ in the Library.`,
      action: { label: 'Upload in the Library →', to: 'library' },
    }
  }
  return { step: 'make', title, detail, action: { label: 'Make a batch →', to: 'studio/make' } }
}

/** The one current step and its action (priorities above). */
export function currentFocus({ standing, hasApprovedSchedule, paused, update, make, now }: FocusInput): Focus {
  const t = now.getTime()
  if (standing && standing.awaitingReview > 0) {
    const n = standing.awaitingReview
    return {
      step: 'review',
      title: `Review ${plural(n, 'episode')}`,
      detail: 'Watch each one, leave feedback and approve the ones that are ready.',
      action: { label: `Review ${n} →`, to: 'library' },
    }
  }
  if (standing?.lastBatch && standing.lastBatch.awaitingFiles > 0) {
    const { batchId, awaitingFiles } = standing.lastBatch
    return {
      step: 'upload',
      title: `Finish uploading ${batchId}`,
      detail: `${plural(awaitingFiles, 'episode')} still ${awaitingFiles === 1 ? 'needs' : 'need'} a video or cover. Drop the folder again: files already on the Pi are skipped.`,
      action: { label: 'Upload in the Library →', to: 'library' },
    }
  }
  if (standing && !standing.lastBatch) {
    return makeFocus(
      standing,
      make,
      'Make the first batch',
      'Copy the prompt into Claude on the Mac, follow the checkpoints, then upload the finalized folder in the Library.',
    )
  }
  if (!hasApprovedSchedule) {
    return {
      step: 'schedule',
      title: 'Draft a schedule',
      detail: 'Generate a draft from the recommended plan, check it, then approve it. After that the autopilot keeps it filled.',
      action: { label: 'Open Schedule →', to: 'schedule' },
    }
  }
  if (standing) {
    const old = stale(standing, t)
    const started = Boolean(make?.started && make.batchId === standing.nextBatchId)
    const ending = runningOut(standing, t)
    if (old || !runway(standing, t) || ending || started) {
      const next = standing.nextBatchId ? ` (${standing.nextBatchId})` : ''
      return makeFocus(
        standing,
        make,
        `Make the next batch${next}`,
        old
          ? `The last batch is over ${STALE_BATCH_DAYS / 7} weeks old. Start the next one from your feedback.`
          : !runway(standing, t)
            ? `Nothing is scheduled in the next ${RUNWAY_DAYS} days. Make more content from your feedback.`
            : ending && standing.contentThrough && standing.nextBatchBy
              ? `Approved posts run out after ${formatDayHeading(standing.contentThrough)}. Upload and approve the next batch by ${formatDayHeading(standing.nextBatchBy)} so the autopilot's refill finds it.`
              : 'You started it in this browser. Follow the checklist; the batch counts once it is uploaded.',
      )
    }
  }
  if (paused) {
    return {
      step: 'post',
      title: 'Start posting (owner command)',
      detail: 'Publishing and the autopilot are paused. Resuming is the owner’s sudo command on the Pi; Settings › Activation shows it with the checklist.',
      action: { label: 'Open Activation →', to: 'settings#activation' },
    }
  }
  if (updateAvailable(update)) {
    const behind = update?.status.check?.behind ?? 0
    return {
      step: 'post',
      title: 'Update the Pi',
      detail: `${plural(behind, 'update')} waiting from the last check.`,
      action: { label: 'Open Settings › Update →', to: 'settings#update' },
    }
  }
  if (standing && (standing.openFeedback > 0 || retroWaiting(standing))) {
    return {
      step: 'learn',
      title: 'Carry feedback into the next batch',
      detail: `${standing.openFeedback > 0 ? `${plural(standing.openFeedback, 'open feedback note')}` : 'The last retro is newer than the last brief'}. Use it for the next brief when you are ready.`,
      action: { label: 'Make a batch →', to: 'studio/make' },
    }
  }
  return { step: 'post', title: 'Nothing needs you right now', detail: 'Posts go out on schedule. Check back after the next ones.', action: null }
}

function shortDate(iso: string, zone: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso.slice(0, 10)
  try {
    return new Intl.DateTimeFormat('en-GB', { timeZone: zone, day: 'numeric', month: 'short' }).format(date)
  } catch {
    return iso.slice(0, 10)
  }
}

/** Full step states for the loop strip (null until the dashboard has loaded). */
export function journey(args: { dashboard: DashboardResponse | null | undefined; update: UpdateInfo | null; make: MakeProgress | null; now: Date }): Journey | null {
  const { dashboard, update, make, now } = args
  if (!dashboard) return null
  const standing: Standing | null = dashboard.standing ?? null
  const approved = dashboard.approval.manifestSha256 !== null
  const focus = currentFocus({ standing, hasApprovedSchedule: approved, paused: dashboard.paused, update, make, now })
  const zone = dashboard.displayTimezone
  const last = standing?.lastBatch ?? null
  const t = now.getTime()

  const base: Record<StepId, { state: Exclude<StepState, 'current'>; fact: string }> = {
    make: last
      ? { state: 'done', fact: `${last.batchId} · ${plural(last.episodeCount, 'episode')} · ${shortDate(last.importedAt, zone)}` }
      : { state: 'todo', fact: 'No batch from the Mac yet' },
    upload: !last
      ? { state: 'todo', fact: 'Nothing uploaded yet' }
      : last.awaitingFiles > 0
        ? { state: 'todo', fact: `${plural(last.awaitingFiles, 'episode')} of ${last.batchId} missing files` }
        : { state: 'done', fact: `${last.batchId} uploaded` },
    review:
      standing && standing.awaitingReview > 0
        ? { state: 'todo', fact: `${standing.awaitingReview} to review` }
        : last
          ? { state: 'done', fact: 'Nothing waiting for review' }
          : { state: 'todo', fact: 'Nothing to review yet' },
    schedule: !approved
      ? { state: 'todo', fact: 'No approved schedule' }
      : standing && !runway(standing, t)
        ? { state: 'todo', fact: `Approved, but nothing in the next ${RUNWAY_DAYS} days` }
        : { state: 'done', fact: `Approved · ${plural(standing?.nextPosts.length ?? 0, 'post')} coming up` },
    post: dashboard.paused
      ? { state: 'blocked', fact: 'Paused · owner command, see Settings' }
      : standing && (standing.nextPosts.length > 0 || standing.postedLast7Days > 0)
        ? { state: 'done', fact: `Running · ${standing.postedLast7Days} posted in the last 7 days` }
        : { state: 'todo', fact: 'Running · nothing scheduled' },
    learn:
      standing && standing.openFeedback > 0
        ? { state: 'todo', fact: plural(standing.openFeedback, 'open feedback note') }
        : standing && retroWaiting(standing)
          ? { state: 'todo', fact: 'A new retro is waiting for the next brief' }
          : last
            ? { state: 'done', fact: 'No open feedback' }
            : { state: 'todo', fact: 'Feedback appears after the first review' },
  }

  const steps: JourneyStep[] = STEPS.map((s) => {
    const { state, fact } = base[s.id]
    // A blocked step stays blocked when it is the focus: the hero says why and who.
    return { id: s.id, n: s.n, label: s.label, mac: s.mac, fact, state: s.id === focus.step && state !== 'blocked' ? 'current' : state }
  })
  const current = steps.find((s) => s.id === focus.step) ?? (steps[0] as JourneyStep)
  return { steps, focus, current }
}

/** Screens and the steps they belong to (first listed = the default when none of them is current). */
export const SCREEN_STEPS = {
  studio: ['make'],
  export: ['make'],
  newFormat: ['make'],
  jobs: ['make'],
  job: ['make'],
  renders: ['make'],
  storySettings: ['make'],
  make: ['make', 'learn'],
  library: ['upload', 'review'],
  episode: ['review'],
  schedule: ['schedule'],
  queue: ['schedule'],
  activity: ['post'],
  settings: ['post'],
} as const satisfies Record<string, readonly StepId[]>

export type StepScreen = keyof typeof SCREEN_STEPS | 'home'

function stepMeta(id: StepId): (typeof STEPS)[number] {
  return STEPS.find((s) => s.id === id) ?? STEPS[0]
}

/** The step a screen shows in its step line: Home shows the focus; other screens their own (current one first). */
export function screenStep(screen: StepScreen, j: Journey | null): { id: StepId; n: number; label: string; state: StepState | null } | null {
  if (screen === 'home') return j ? { ...j.current } : null
  const ids: readonly StepId[] = SCREEN_STEPS[screen]
  const live = j ? ids.map((id) => j.steps.find((s) => s.id === id)).filter((s): s is JourneyStep => Boolean(s)) : []
  const pick = live.find((s) => s.state === 'current') ?? live[0]
  // Make a batch is always about the next batch: the last one being "done" says nothing there.
  if (pick) return { id: pick.id, n: pick.n, label: pick.label, state: screen === 'make' && pick.state === 'done' ? null : pick.state }
  const meta = stepMeta(ids[0] ?? 'make')
  return { id: meta.id, n: meta.n, label: meta.label, state: null }
}
