import { describe, expect, it } from 'vitest'
import type { DashboardResponse, Standing } from '../api/types'
import { dashboardFixture, SHA, updateInfo } from '../test/fixtures'
import { journey, screenStep, type Journey, type StepId, type StepState } from './journey'
import type { MakeProgress } from './makeChecklist'

const now = new Date('2026-10-08T12:00:00Z')
const SOON = '2026-10-10T13:00:00Z'

/** Dashboard fixture with an approved schedule, posts coming up, nothing to review and publishing running. */
function steady(standing: Partial<Standing> = {}, over: Partial<DashboardResponse> = {}): DashboardResponse {
  const d = dashboardFixture()
  return {
    ...d,
    paused: false,
    approval: { ...d.approval, manifestSha256: SHA, approvedAt: '2026-10-07T21:40:00Z', bound: true },
    standing: {
      ...d.standing,
      awaitingReview: 0,
      openFeedback: 0,
      nextPosts: [{ at: SOON, platform: 'threads', episodeId: 'scalar-clues-001' }],
      postedLast7Days: 3,
      ...standing,
    },
    ...over,
  }
}

const make = (over: Partial<MakeProgress> = {}): MakeProgress => ({ batchId: '2026-10-b02', started: false, checks: [], ...over })

function states(j: Journey | null): Record<StepId, StepState> {
  return Object.fromEntries((j?.steps ?? []).map((s) => [s.id, s.state])) as Record<StepId, StepState>
}

function run(dashboard: DashboardResponse, extra: { make?: MakeProgress | null; update?: ReturnType<typeof updateInfo> | null } = {}) {
  const j = journey({ dashboard, update: extra.update ?? null, make: extra.make ?? null, now })
  if (!j) throw new Error('journey should not be null')
  return j
}

describe('journey: one progress model for the loop', () => {
  it('is null until the dashboard has loaded', () => {
    expect(journey({ dashboard: null, update: null, make: null, now })).toBeNull()
  })

  it('always has six steps in loop order and exactly one focus', () => {
    const j = run(dashboardFixture())
    expect(j.steps.map((s) => `${s.n}:${s.label}`)).toEqual(['1:Make', '2:Upload', '3:Review', '4:Schedule', '5:Post', '6:Learn'])
    expect(j.steps.filter((s) => s.state === 'current')).toHaveLength(1)
    expect(j.current.id).toBe(j.focus.step)
    expect(j.steps[0]?.mac).toBe(true)
  })

  it('Review is current while episodes wait (fixture: 3 to review, paused, no schedule)', () => {
    const j = run(dashboardFixture())
    expect(j.focus).toMatchObject({ step: 'review', title: 'Review 3 episodes', action: { label: 'Review 3 →', to: 'library' } })
    expect(states(j)).toEqual({ make: 'done', upload: 'done', review: 'current', schedule: 'todo', post: 'blocked', learn: 'todo' })
    const byId = Object.fromEntries(j.steps.map((s) => [s.id, s.fact]))
    expect(byId.make).toBe('2026-10-b01 · 12 episodes · 5 Oct')
    expect(byId.review).toBe('3 to review')
    expect(byId.post).toBe('Paused · owner command, see Settings')
    expect(byId.learn).toBe('2 open feedback notes')
  })

  it('Upload is current while the last batch misses files', () => {
    const d = dashboardFixture()
    const j = run({ ...d, standing: { ...d.standing, awaitingReview: 0, lastBatch: { batchId: '2026-10-b01', importedAt: '2026-10-05T18:00:00Z', episodeCount: 12, awaitingFiles: 2 } } })
    expect(j.focus).toMatchObject({ step: 'upload', title: 'Finish uploading 2026-10-b01', action: { to: 'library' } })
    expect(j.focus.detail).toMatch(/^2 episodes still need a video or cover/)
    expect(states(j)).toMatchObject({ make: 'done', upload: 'current', review: 'done' })
  })

  it('Make is current before the first batch; Upload takes over once the Mac checklist is finalized', () => {
    const d = dashboardFixture()
    const empty = { ...d, standing: { ...d.standing, lastBatch: null, awaitingReview: 0, openFeedback: 0 } }
    const first = run(empty)
    expect(first.focus).toMatchObject({ step: 'make', title: 'Make the first batch', action: { label: 'Make a batch →', to: 'studio/make' } })
    expect(states(first)).toEqual({ make: 'current', upload: 'todo', review: 'todo', schedule: 'todo', post: 'blocked', learn: 'todo' })
    expect(first.steps.find((s) => s.id === 'make')?.fact).toBe('No batch from the Mac yet')

    const finalized = run(empty, { make: make({ started: true, checks: ['c0', 'c1', 'c3', 'finalize'] }) })
    expect(finalized.focus).toMatchObject({ step: 'upload', title: 'Finalize and upload 2026-10-b02', action: { to: 'library' } })
    expect(states(finalized)).toMatchObject({ make: 'todo', upload: 'current' })
  })

  it('Schedule is current when nothing is approved', () => {
    const j = run(steady({}, { approval: dashboardFixture().approval }))
    expect(j.focus).toMatchObject({ step: 'schedule', title: 'Draft a schedule', action: { to: 'schedule' } })
    expect(states(j)).toMatchObject({ schedule: 'current' })
    expect(j.steps.find((s) => s.id === 'schedule')?.fact).toBe('No approved schedule')
  })

  it('Make the next batch when the runway is empty, the batch is stale, or the next batch was started here', () => {
    const empty = run(steady({ nextPosts: [] }))
    expect(empty.focus).toMatchObject({ step: 'make', title: 'Make the next batch (2026-10-b02)', action: { to: 'studio/make' } })
    expect(empty.focus.detail).toMatch(/next 14 days/)
    expect(states(empty)).toMatchObject({ make: 'current', schedule: 'todo' })
    expect(empty.steps.find((s) => s.id === 'schedule')?.fact).toBe('Approved, but nothing in the next 14 days')

    const d = steady({ lastBatch: { batchId: '2026-08-b01', importedAt: '2026-08-01T00:00:00Z', episodeCount: 8, awaitingFiles: 0 } })
    expect(run(d).focus.detail).toMatch(/over 6 weeks old/)

    const started = run(steady(), { make: make({ started: true }) })
    expect(started.focus).toMatchObject({ step: 'make', detail: expect.stringMatching(/started it in this browser/) })
    // A checklist for some other id does not count.
    expect(run(steady(), { make: make({ batchId: '2026-10-b09', started: true }) }).focus.step).toBe('post')
    // Finalized on the Mac → upload it.
    expect(run(steady(), { make: make({ started: true, checks: ['finalize'] }) }).focus.title).toBe('Finalize and upload 2026-10-b02')
  })

  it('Post is the focus and blocked while paused: activation is the owner’s command', () => {
    const j = run(steady({}, { paused: true }))
    expect(j.focus).toMatchObject({ step: 'post', title: 'Start posting (owner command)', action: { to: 'settings#activation' } })
    expect(j.current).toMatchObject({ id: 'post', state: 'blocked' })
    expect(states(j)).toEqual({ make: 'done', upload: 'done', review: 'done', schedule: 'done', post: 'blocked', learn: 'done' })
    expect(j.steps.filter((s) => s.state === 'current')).toHaveLength(0)
  })

  it('an available update is the next housekeeping step, kept with Post', () => {
    const j = run(steady(), { update: updateInfo() })
    expect(j.focus).toMatchObject({ step: 'post', title: 'Update the Pi', detail: '2 updates waiting from the last check.', action: { to: 'settings#update' } })
    expect(j.current.state).toBe('current')
  })

  it('Learn is current with open feedback or a retro newer than the last brief', () => {
    const feedback = run(steady({ openFeedback: 1 }))
    expect(feedback.focus).toMatchObject({ step: 'learn', title: 'Carry feedback into the next batch', action: { to: 'studio/make' } })
    expect(feedback.focus.detail).toMatch(/^1 open feedback note\./)
    expect(states(feedback)).toMatchObject({ learn: 'current', post: 'done' })

    const retro = run(steady({ lastBriefAt: '2026-10-01T10:00:00Z', lastRetroAt: '2026-10-07T10:00:00Z' }))
    expect(retro.focus.step).toBe('learn')
    expect(retro.focus.detail).toMatch(/retro is newer/)
    expect(run(steady({ lastBriefAt: '2026-10-07T10:00:00Z', lastRetroAt: '2026-10-01T10:00:00Z' })).focus.step).toBe('post')
  })

  it('otherwise Post is current with nothing to do', () => {
    const j = run(steady())
    expect(j.focus).toMatchObject({ step: 'post', title: 'Nothing needs you right now', action: null })
    expect(states(j)).toEqual({ make: 'done', upload: 'done', review: 'done', schedule: 'done', post: 'current', learn: 'done' })
    expect(j.steps.find((s) => s.id === 'post')?.fact).toBe('Running · 3 posted in the last 7 days')
    expect(j.steps.find((s) => s.id === 'schedule')?.fact).toBe('Approved · 1 post coming up')
  })

  it('Post is todo while running with nothing scheduled or posted', () => {
    const j = run(steady({ nextPosts: [], postedLast7Days: 0 }))
    expect(j.steps.find((s) => s.id === 'post')).toMatchObject({ state: 'todo', fact: 'Running · nothing scheduled' })
  })
})

describe('screenStep: the step line under each title', () => {
  it('Home shows the focus; screens show their own step, preferring the current one', () => {
    const j = run(dashboardFixture())
    expect(screenStep('home', j)).toMatchObject({ n: 3, label: 'Review', state: 'current' })
    expect(screenStep('library', j)).toMatchObject({ n: 3, label: 'Review', state: 'current' })
    expect(screenStep('make', j)).toMatchObject({ n: 1, label: 'Make', state: null })
    expect(screenStep('schedule', j)).toMatchObject({ n: 4, label: 'Schedule', state: 'todo' })
    expect(screenStep('settings', j)).toMatchObject({ n: 5, label: 'Post', state: 'blocked' })
    expect(screenStep('activity', j)).toMatchObject({ n: 5, label: 'Post' })
    expect(screenStep('episode', j)).toMatchObject({ n: 3, label: 'Review' })
  })

  it('works before the dashboard loads (no state), except on Home', () => {
    expect(screenStep('home', null)).toBeNull()
    expect(screenStep('library', null)).toEqual({ id: 'upload', n: 2, label: 'Upload', state: null })
    expect(screenStep('make', null)).toEqual({ id: 'make', n: 1, label: 'Make', state: null })
  })
})
