/**
 * Pure state for Settings → Update (REBUILD_CONTRACTS.md §1). The UI only reads local status and
 * queues requests; the updater service on the Pi does the fetching, testing and switching.
 */
import type { UnitsApply, UpdateCheck, UpdateInfo, UpdatePhase } from '../api/types'

export const UPDATE_POLL_MS = 2_000
/** The server refuses to start from a check older than this. */
export const CHECK_MAX_AGE_MS = 15 * 60_000
/** Give up waiting for a check that never finishes. */
export const CHECK_TIMEOUT_MS = 3 * 60_000
/** Give up following an update (the staged tests and the publisher lock can take ~10 min). */
export const WATCH_GIVE_UP_MS = 30 * 60_000
export const DEFAULT_APPLY_UNITS_COMMAND = 'sudo /opt/scalar-social/repo/publisher/deploy/apply-units.sh'

/** A queued automatic apply that has not started within this long means the apply path unit is not installed yet. */
export const AUTO_APPLY_STALE_MS = 10 * 60_000

/**
 * What the Update screen says about unit/package changes: the automatic apply (units-apply.json for the checkout's
 * commit) is working, failed or done; or, with no record or a queued run that never started, the owner runs
 * apply-units.sh by hand. null: nothing to say.
 */
export function unitsApplyState(info: UpdateInfo, auto: UnitsApply | null, now: number): 'working' | 'failed' | 'done' | 'manual' | null {
  const changed = info.unitsChanged || info.piPackageChanged
  if (!changed) return auto?.phase === 'ok' ? 'done' : null
  if (auto?.phase === 'running') return 'working'
  if (auto?.phase === 'queued' && auto.at && now - Date.parse(auto.at) < AUTO_APPLY_STALE_MS) return 'working'
  if (auto?.phase === 'failed') return 'failed'
  return 'manual'
}

export function changedWords(info: UpdateInfo): string {
  if (info.unitsChanged && info.piPackageChanged) return 'unit file and pi-package changes'
  return info.unitsChanged ? 'unit file changes' : 'pi-package changes'
}

/** Phases during which a started update is in progress (check and start are refused). */
export const BUSY_PHASES: readonly UpdatePhase[] = ['staging', 'waiting', 'switching', 'switched', 'restarting']

export function isBusy(phase: UpdatePhase): boolean {
  return BUSY_PHASES.includes(phase)
}

/** Phase in plain words. An unreachable server during an update means it is restarting. */
export function phaseWords(phase: UpdatePhase, reachable = true): string {
  if (!reachable) return 'Restarting…'
  switch (phase) {
    case 'idle':
      return 'No update running.'
    case 'checking':
      return 'Checking GitHub for updates…'
    case 'checked':
      return 'Check finished.'
    case 'staging':
      return 'Downloading and testing the update…'
    case 'waiting':
      return 'Waiting for the publisher to finish a post…'
    case 'switching':
      return 'Switching to the new version…'
    case 'switched':
    case 'restarting':
      return 'Restarting…'
    case 'complete':
      return 'Update complete.'
    case 'failed':
      return 'Update failed.'
  }
}

export function checkAgeMs(check: UpdateCheck, now: number): number {
  const at = Date.parse(check.checkedAt)
  return Number.isNaN(at) ? Infinity : now - at
}

export function updateAvailable(info: UpdateInfo | null): boolean {
  const check = info?.status.check
  return Boolean(check && check.fetchOk && check.behind > 0 && check.origin)
}

export interface CheckProblem {
  id: 'fetch' | 'dirty' | 'diverged' | 'branch' | 'origin'
  title: string
  next: string
}

/** Warnings from the last check, each with a plain next step. */
export function checkProblems(check: UpdateCheck | null): CheckProblem[] {
  if (!check) return []
  const out: CheckProblem[] = []
  if (!check.fetchOk)
    out.push({
      id: 'fetch',
      title: `The Pi could not reach GitHub${check.error ? `: ${check.error}` : '.'}`,
      next: 'Check the Pi’s internet connection and its deploy key, then press Check for updates again.',
    })
  if (check.dirty)
    out.push({
      id: 'dirty',
      title: 'The Pi’s copy of the code has local edits.',
      next: 'Updating is blocked so nothing is lost. Ask the owner to inspect and reset the checkout (Guide → Failed update).',
    })
  if (check.diverged)
    out.push({
      id: 'diverged',
      title: `The Pi has ${check.ahead} commit${check.ahead === 1 ? '' : 's'} that GitHub does not.`,
      next: 'A fast-forward is impossible. The owner must reconcile the checkout (Guide → Failed update).',
    })
  if (!check.branchOk)
    out.push({
      id: 'branch',
      title: 'The Pi’s checkout is not on the main branch.',
      next: 'The owner switches it back to main, then check again.',
    })
  if (!check.originOk)
    out.push({
      id: 'origin',
      title: `The checkout points at an unexpected repository (${check.originUrl || 'none'}).`,
      next: 'The owner sets the origin back to the marketing repository (Guide → Update the Pi).',
    })
  return out
}

export interface Gate {
  allowed: boolean
  reason: string | null
}

/** Whether "Update" may be offered, mirroring the server's start requirements. */
export function startGate(info: UpdateInfo | null, now: number): Gate {
  if (!info) return { allowed: false, reason: 'Update status not loaded.' }
  if (info.installKind !== 'git') return { allowed: false, reason: 'This Pi still runs the copied install.' }
  const { phase, check } = info.status
  if (phase === 'checking' || isBusy(phase)) return { allowed: false, reason: 'An update request is already running.' }
  if (!check) return { allowed: false, reason: 'Check for updates first.' }
  if (checkProblems(check).length) return { allowed: false, reason: 'Resolve the warnings below first.' }
  if (!check.origin || check.behind <= 0) return { allowed: false, reason: 'Already up to date.' }
  if (checkAgeMs(check, now) > CHECK_MAX_AGE_MS) return { allowed: false, reason: 'The last check is older than 15 minutes; check again.' }
  return { allowed: true, reason: null }
}

/** Snapshot taken just before queueing a check. */
export interface CheckMarker {
  updatedAt: string | null
  checkedAt: string | null
}

export function checkMarker(info: UpdateInfo | null): CheckMarker {
  return { updatedAt: info?.status.updatedAt ?? null, checkedAt: info?.status.check?.checkedAt ?? null }
}

/**
 * A queued check has finished once the updater has touched the status since it was queued and
 * the phase is no longer `checking` (the request may sit queued for a moment before that).
 */
export function checkSettled(before: CheckMarker, info: UpdateInfo): boolean {
  if (info.status.phase === 'checking') return false
  return info.status.updatedAt !== before.updatedAt || (info.status.check?.checkedAt ?? null) !== before.checkedAt
}

// ---------------------------------------------------------------------------
// Following a started update across the UI restart (sessionStorage baseline)
// ---------------------------------------------------------------------------

export const BASELINE_KEY = 'scalar-update-baseline'
export const UPDATED_KEY = 'scalar-update-done'

export interface UpdateBaseline {
  /** Commit the UI was running when this device started the update. */
  runningCommit: string | null
  /** Client clock (ms) when the start request was accepted. */
  startedAt: number
  /** status.updatedAt before starting: a failure only counts once the status changed. */
  statusUpdatedAt?: string | null
}

export function readBaseline(storage: Storage | null = safeSession()): UpdateBaseline | null {
  try {
    const raw = storage?.getItem(BASELINE_KEY)
    if (!raw) return null
    const data = JSON.parse(raw) as Partial<UpdateBaseline>
    if (typeof data.startedAt !== 'number') return null
    return { runningCommit: typeof data.runningCommit === 'string' ? data.runningCommit : null, startedAt: data.startedAt, statusUpdatedAt: data.statusUpdatedAt ?? null }
  } catch {
    return null
  }
}

export function writeBaseline(baseline: UpdateBaseline, storage: Storage | null = safeSession()): void {
  try {
    storage?.setItem(BASELINE_KEY, JSON.stringify(baseline))
  } catch {
    // Storage blocked: the watch still works while this page stays open.
  }
}

export function clearBaseline(storage: Storage | null = safeSession()): void {
  try {
    storage?.removeItem(BASELINE_KEY)
  } catch {
    // ignore
  }
}

function safeSession(): Storage | null {
  try {
    return typeof sessionStorage === 'undefined' ? null : sessionStorage
  } catch {
    return null
  }
}

/**
 * Reload only on a reply fetched after the update started whose running commit differs from the
 * baseline (an unreachable server or an older reply never triggers it).
 */
export function shouldReload(baseline: UpdateBaseline | null, runningCommit: string | null, fetchedAt: number): boolean {
  return Boolean(baseline && fetchedAt > baseline.startedAt && runningCommit && runningCommit !== baseline.runningCommit)
}

export type WatchOutcome =
  | { kind: 'reload'; commit: string }
  | { kind: 'failed'; error: string }
  | { kind: 'waiting'; label: string }
  | { kind: 'gave-up' }

export function watchOutcome(args: {
  baseline: UpdateBaseline
  info: UpdateInfo | null
  reachable: boolean
  fetchedAt: number
  now: number
}): WatchOutcome {
  const { baseline, info, reachable, fetchedAt, now } = args
  if (reachable && info && shouldReload(baseline, info.runningCommit, fetchedAt)) return { kind: 'reload', commit: info.runningCommit as string }
  const fresh = reachable && info !== null && fetchedAt > baseline.startedAt
  if (fresh && info && info.status.phase === 'failed' && info.status.updatedAt !== (baseline.statusUpdatedAt ?? null))
    return { kind: 'failed', error: info.status.error ?? 'The update failed without a message.' }
  if (now - baseline.startedAt > WATCH_GIVE_UP_MS) return { kind: 'gave-up' }
  if (!reachable || !info) return { kind: 'waiting', label: phaseWords('restarting', false) }
  const label = info.status.phase === 'checked' || info.status.phase === 'idle' ? 'Starting the update…' : phaseWords(info.status.phase)
  return { kind: 'waiting', label }
}

/** Which kind of polling the Update section needs right now. */
export type PollMode = 'none' | 'check' | 'watch' | 'busy'

export function pollMode(args: { info: UpdateInfo | null; baseline: UpdateBaseline | null; checkPending: boolean }): PollMode {
  if (args.baseline) return 'watch'
  if (args.checkPending) return 'check'
  const phase = args.info?.status.phase
  if (phase === 'checking') return 'check'
  if (phase && isBusy(phase)) return 'busy'
  // The automatic unit apply runs after the update finished: keep refreshing until it is done (it restarts the UI).
  const auto = args.info?.unitsApply
  if (auto && auto.commit === args.info?.repoHead && (auto.phase === 'queued' || auto.phase === 'running')) return 'busy'
  return 'none'
}
