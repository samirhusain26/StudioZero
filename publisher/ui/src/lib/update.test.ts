import { describe, expect, it } from 'vitest'
import { ORIGIN, RUNNING, updateInfo } from '../test/fixtures'
import {
  BASELINE_KEY,
  checkMarker,
  checkProblems,
  checkSettled,
  clearBaseline,
  phaseWords,
  pollMode,
  readBaseline,
  shouldReload,
  startGate,
  updateAvailable,
  watchOutcome,
  WATCH_GIVE_UP_MS,
  writeBaseline,
  type UpdateBaseline,
} from './update'

const NOW = Date.parse('2026-10-20T12:00:00Z')

describe('phaseWords', () => {
  it('describes every phase in plain words; unreachable means restarting', () => {
    expect(phaseWords('staging')).toBe('Downloading and testing the update…')
    expect(phaseWords('waiting')).toBe('Waiting for the publisher to finish a post…')
    expect(phaseWords('switching')).toBe('Switching to the new version…')
    expect(phaseWords('restarting')).toBe('Restarting…')
    expect(phaseWords('failed')).toBe('Update failed.')
    expect(phaseWords('staging', false)).toBe('Restarting…')
  })
})

describe('start gate', () => {
  it('allows Update only for a fresh, clean check that is behind', () => {
    expect(startGate(updateInfo(), NOW)).toEqual({ allowed: true, reason: null })
    expect(updateAvailable(updateInfo())).toBe(true)
    expect(startGate(updateInfo({ check: { checkedAt: '2026-10-20T11:40:00Z' } }), NOW).reason).toMatch(/older than 15 minutes/)
    expect(startGate(updateInfo({ check: { behind: 0 } }), NOW).reason).toBe('Already up to date.')
    expect(startGate(updateInfo({ check: { dirty: true } }), NOW).allowed).toBe(false)
    expect(startGate(updateInfo({ check: { diverged: true, ahead: 1 } }), NOW).allowed).toBe(false)
    expect(startGate(updateInfo({ check: null }), NOW).reason).toBe('Check for updates first.')
    expect(startGate(updateInfo({ installKind: 'copy' }), NOW).allowed).toBe(false)
    expect(startGate(updateInfo({ status: { phase: 'staging' } }), NOW).allowed).toBe(false)
    expect(startGate(null, NOW).allowed).toBe(false)
  })

})

describe('checkProblems', () => {
  it('turns each blocking condition into a warning with a next step', () => {
    const check = updateInfo({ check: { fetchOk: false, error: 'ssh: connect timed out', dirty: true, diverged: true, ahead: 2, branchOk: false, originOk: false } }).status.check
    const problems = checkProblems(check)
    expect(problems.map((p) => p.id)).toEqual(['fetch', 'dirty', 'diverged', 'branch', 'origin'])
    expect(problems[0]?.title).toContain('ssh: connect timed out')
    expect(problems[2]?.title).toBe('The Pi has 2 commits that GitHub does not.')
    for (const p of problems) expect(p.next.length).toBeGreaterThan(10)
    expect(checkProblems(updateInfo().status.check)).toEqual([])
    expect(checkProblems(null)).toEqual([])
  })
})

describe('check polling', () => {
  it('waits until the updater has touched the status and left `checking`', () => {
    const before = checkMarker(updateInfo())
    // Still queued: nothing changed yet.
    expect(checkSettled(before, updateInfo())).toBe(false)
    expect(checkSettled(before, updateInfo({ status: { phase: 'checking', updatedAt: '2026-10-20T12:00:01Z' } }))).toBe(false)
    expect(checkSettled(before, updateInfo({ status: { updatedAt: '2026-10-20T12:00:05Z' }, check: { checkedAt: '2026-10-20T12:00:05Z' } }))).toBe(true)
    expect(checkSettled(before, updateInfo({ status: { phase: 'failed', updatedAt: '2026-10-20T12:00:05Z' } }))).toBe(true)
  })

  it('chooses the poll mode', () => {
    const baseline: UpdateBaseline = { runningCommit: RUNNING, startedAt: NOW }
    expect(pollMode({ info: updateInfo(), baseline: null, checkPending: false })).toBe('none')
    expect(pollMode({ info: updateInfo(), baseline: null, checkPending: true })).toBe('check')
    expect(pollMode({ info: updateInfo({ status: { phase: 'checking' } }), baseline: null, checkPending: false })).toBe('check')
    expect(pollMode({ info: updateInfo({ status: { phase: 'waiting' } }), baseline: null, checkPending: false })).toBe('busy')
    expect(pollMode({ info: null, baseline, checkPending: false })).toBe('watch')
  })
})

describe('reload on commit change', () => {
  const baseline: UpdateBaseline = { runningCommit: RUNNING, startedAt: NOW, statusUpdatedAt: '2026-10-20T11:55:00Z' }

  it('reloads only for a reply fetched after start whose running commit changed', () => {
    expect(shouldReload(baseline, ORIGIN, NOW + 2000)).toBe(true)
    expect(shouldReload(baseline, ORIGIN, NOW - 1)).toBe(false)
    expect(shouldReload(baseline, RUNNING, NOW + 2000)).toBe(false)
    expect(shouldReload(baseline, null, NOW + 2000)).toBe(false)
    expect(shouldReload(null, ORIGIN, NOW + 2000)).toBe(false)
  })

  it('follows the update through restart, success, failure and give-up', () => {
    const at = NOW + 4000
    expect(watchOutcome({ baseline, info: null, reachable: false, fetchedAt: at, now: at })).toEqual({ kind: 'waiting', label: 'Restarting…' })
    expect(watchOutcome({ baseline, info: updateInfo({ status: { phase: 'staging' } }), reachable: true, fetchedAt: at, now: at })).toEqual({
      kind: 'waiting',
      label: 'Downloading and testing the update…',
    })
    // An old failure (status unchanged since start) is not this attempt's result.
    expect(watchOutcome({ baseline, info: updateInfo({ status: { phase: 'failed', error: 'old' } }), reachable: true, fetchedAt: at, now: at }).kind).toBe('waiting')
    expect(
      watchOutcome({ baseline, info: updateInfo({ status: { phase: 'failed', error: 'Staged tests failed', updatedAt: '2026-10-20T12:01:00Z' } }), reachable: true, fetchedAt: at, now: at }),
    ).toEqual({ kind: 'failed', error: 'Staged tests failed' })
    expect(watchOutcome({ baseline, info: updateInfo({ runningCommit: ORIGIN, status: { phase: 'complete' } }), reachable: true, fetchedAt: at, now: at })).toEqual({
      kind: 'reload',
      commit: ORIGIN,
    })
    expect(watchOutcome({ baseline, info: null, reachable: false, fetchedAt: at, now: NOW + WATCH_GIVE_UP_MS + 1 })).toEqual({ kind: 'gave-up' })
  })

  it('stores the baseline in sessionStorage', () => {
    writeBaseline({ runningCommit: RUNNING, startedAt: NOW, statusUpdatedAt: null })
    expect(JSON.parse(sessionStorage.getItem(BASELINE_KEY) ?? '{}')).toMatchObject({ runningCommit: RUNNING, startedAt: NOW })
    expect(readBaseline()).toEqual({ runningCommit: RUNNING, startedAt: NOW, statusUpdatedAt: null })
    clearBaseline()
    expect(readBaseline()).toBeNull()
    sessionStorage.setItem(BASELINE_KEY, 'not json')
    expect(readBaseline()).toBeNull()
  })
})
