import { describe, expect, it } from 'vitest'
import type { Standing, UpdateInfo } from '../api/types'
import { nextStep } from './nextStep'

const now = new Date('2026-10-20T12:00:00Z')
const standing = (over: Partial<Standing> = {}): Standing => ({
  lastBatch: { batchId: '2026-10-b01', importedAt: '2026-10-10T12:00:00Z', episodeCount: 12, awaitingFiles: 0 },
  awaitingReview: 0,
  nextPosts: [{ at: '2026-10-22T13:00:00Z', platform: 'instagram', episodeId: 'scalar-clues-001' }],
  openFeedback: 0,
  nextBatchId: '2026-10-b02',
  postedLast7Days: 0,
  lastBriefAt: null,
  lastRetroAt: null,
  contentThrough: null,
  nextBatchBy: null,
  ...over,
})
const update = (behind: number): UpdateInfo => ({
  runningCommit: 'a'.repeat(40),
  installKind: 'git',
  repoHead: 'a'.repeat(40),
  restartNeeded: false,
  unitsChanged: false,
  piPackageChanged: false,
  applyUnitsCommand: null,
  unitsApply: null,
  status: {
    phase: 'checked', requestId: null, startedAt: null, updatedAt: null, fromCommit: null, toCommit: null, error: null, log: [],
    check: {
      checkedAt: '2026-10-20T11:00:00Z', fetchOk: true, head: 'a'.repeat(40), origin: 'b'.repeat(40), behind, ahead: 0, dirty: false,
      diverged: false, branchOk: true, originOk: true, originUrl: 'git@github.com-scalar:x/y.git', incoming: [],
      changes: { units: false, piPackage: false, contract: false, ui: false, files: [] }, error: null,
    },
  },
})

describe('nextStep (priority order)', () => {
  it('1: review comes first, even with everything else pending', () => {
    const step = nextStep({ standing: standing({ awaitingReview: 4, nextPosts: [] }), hasApprovedSchedule: false, update: update(3), now })
    expect(step).toMatchObject({ step: 'review', title: 'Review 4 episodes', target: 'library' })
    expect(nextStep({ standing: standing({ awaitingReview: 1 }), hasApprovedSchedule: true, update: null, now }).title).toBe('Review 1 episode')
  })

  it('2: no batch at all → make the first batch', () => {
    expect(nextStep({ standing: standing({ lastBatch: null, nextPosts: [] }), hasApprovedSchedule: false, update: null, now })).toMatchObject({
      step: 'make',
      target: 'studio/make',
      title: 'Make the first batch',
    })
  })

  it('3: no approved schedule → draft one', () => {
    expect(nextStep({ standing: standing(), hasApprovedSchedule: false, update: update(2), now })).toMatchObject({
      step: 'schedule',
      title: 'Draft a schedule',
      target: 'schedule',
    })
  })

  it('4: stale batch or no posts within 14 days → next batch', () => {
    const stale = standing({ lastBatch: { batchId: 'old', importedAt: '2026-09-01T00:00:00Z', episodeCount: 5, awaitingFiles: 0 } })
    expect(nextStep({ standing: stale, hasApprovedSchedule: true, update: null, now })).toMatchObject({
      step: 'make',
      title: 'Make the next batch (2026-10-b02)',
      target: 'studio/make',
    })
    const far = standing({ nextPosts: [{ at: '2026-11-20T13:00:00Z', platform: 'x', episodeId: 'e' }] })
    expect(nextStep({ standing: far, hasApprovedSchedule: true, update: null, now }).target).toBe('studio/make')
    expect(nextStep({ standing: standing({ nextPosts: [] }), hasApprovedSchedule: true, update: null, now }).detail).toMatch(/next 14 days/)
  })

  it('5: update available → Settings › Update', () => {
    expect(nextStep({ standing: standing(), hasApprovedSchedule: true, update: update(2), now })).toMatchObject({
      title: 'Update the Pi',
      target: 'settings#update',
      detail: '2 updates waiting from the last check.',
    })
  })

  it('6: nothing to do', () => {
    expect(nextStep({ standing: standing(), hasApprovedSchedule: true, update: update(0), now })).toMatchObject({ target: null })
  })

  it('works without a standing summary (older backend)', () => {
    expect(nextStep({ standing: undefined, hasApprovedSchedule: false, update: null, now }).target).toBe('schedule')
    expect(nextStep({ standing: null, hasApprovedSchedule: true, update: update(1), now }).target).toBe('settings#update')
  })
})
