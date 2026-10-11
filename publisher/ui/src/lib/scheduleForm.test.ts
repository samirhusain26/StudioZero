import { describe, expect, it } from 'vitest'
import { draftResponse } from '../test/fixtures'
import { buildScheduleInputs, emptyScheduleForm, fillSummary, groupDraftJobs, presetForm, presetStartDate, recommendedScheduleForm, withEdit } from './scheduleForm'

describe('schedule generator form', () => {
  it('fills the recommended cadence only when asked, skipping blocked platforms', () => {
    const result = buildScheduleInputs(recommendedScheduleForm('2026-10-31', new Set(['tiktok'])))
    expect(result.ok).toBe(true)
    if (!result.ok) return
    const { inputs } = result
    expect([inputs.timezone, inputs.startDate, inputs.endDate]).toEqual(['America/New_York', '2026-11-01', '2026-11-21'])
    expect(Object.keys(inputs.platforms).sort()).toEqual(['bluesky', 'facebook', 'instagram', 'threads', 'x', 'youtube'])
    expect(inputs.platforms.threads).toEqual({ include: true, weekdays: [0, 1, 2, 3, 4, 5, 6], times: ['09:00'], maxPerDay: 1 })
    expect(inputs.platforms.instagram?.times).toEqual(['18:00'])
    const times = Object.values(inputs.platforms).flatMap((p) => p?.times ?? [])
    expect(times).toHaveLength(6)
    expect(times.every((t) => Number(t.slice(3)) % 15 === 0)).toBe(true)
    expect(new Set(times).size).toBe(times.length)
    expect(inputs.staggerMinutes).toBe(0)
    expect(inputs.companions).toEqual({ firstComment: true, answerReply: true })
  })

  it('the preset path builds exactly the inputs of the old form filled with the preset values (same draft hash)', () => {
    const blocked = new Set(['tiktok'] as const)
    // The old form, filled by hand with the recommended values (what "Use recommended schedule" used to produce).
    const byHand = emptyScheduleForm()
    byHand.timezone = 'America/New_York'
    byHand.startDate = '2026-11-01'
    byHand.endDate = '2026-11-21'
    const times = { threads: '09:00', x: '09:30', bluesky: '10:30', facebook: '12:15', youtube: '16:00', instagram: '18:00' } as const
    for (const [p, t] of Object.entries(times)) {
      byHand.platforms[p as keyof typeof times] = { include: true, weekdays: [6, 5, 4, 3, 2, 1, 0], times: [t], maxPerDay: '1', minGapHours: '2' }
    }
    byHand.staggerMinutes = '0'
    byHand.firstComment = true
    byHand.answerReply = true
    const preset = buildScheduleInputs(presetForm('2026-10-31', blocked, { startDate: presetStartDate('2026-10-31'), timezone: 'America/New_York' }))
    const old = buildScheduleInputs(byHand)
    const tapped = buildScheduleInputs(recommendedScheduleForm('2026-10-31', blocked))
    expect(preset).toEqual(old)
    expect(preset).toEqual(tapped)
    // The draft hash is the server's sha256 over these inputs (+ library and ledger state), so equal inputs give equal hashes.
    expect(JSON.stringify(preset)).toBe(JSON.stringify(old))
  })

  it('the preset follows the two visible fields: start date (21 days from it) and timezone', () => {
    const form = presetForm('2026-10-31', new Set(), { startDate: '2026-12-30', timezone: ' Europe/London ' })
    expect([form.timezone, form.startDate, form.endDate]).toEqual(['Europe/London', '2026-12-30', '2027-01-19'])
    expect(presetForm('2026-10-31', new Set(), { startDate: 'not a date' }).startDate).toBe('2026-11-01')
    expect(presetStartDate('2026-12-31')).toBe('2027-01-01')
  })

  it('starts empty: no timezone, dates, cadence or platforms', () => {
    const form = emptyScheduleForm()
    expect(form.timezone).toBe('')
    expect(form.startDate).toBe('')
    expect(Object.values(form.platforms).every((p) => !p.include && p.weekdays.length === 0 && p.times.length === 0 && p.maxPerDay === '')).toBe(true)
    expect(form.staggerMinutes).toBe('')
    const result = buildScheduleInputs(form)
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.errors).toContain('Enter a timezone (IANA name such as America/New_York).')
      expect(result.errors).toContain('Include at least one platform.')
    }
  })

  it('builds explicit inputs only from what was entered', () => {
    const form = emptyScheduleForm()
    form.timezone = 'America/New_York'
    form.startDate = '2026-10-12'
    form.endDate = '2026-10-25'
    form.platforms.instagram = { include: true, weekdays: [4, 0, 2], times: ['18:30', '09:00'], maxPerDay: '1', minGapHours: '20' }
    form.staggerMinutes = '15'
    form.firstComment = true
    const result = buildScheduleInputs(form)
    expect(result).toEqual({
      ok: true,
      inputs: {
        timezone: 'America/New_York',
        startDate: '2026-10-12',
        endDate: '2026-10-25',
        platforms: { instagram: { include: true, weekdays: [0, 2, 4], times: ['09:00', '18:30'], maxPerDay: 1 } },
        minGapHours: { instagram: 20 },
        staggerMinutes: 15,
        ordering: 'game-round-robin',
        companions: { firstComment: true, answerReply: false },
        edits: {},
      },
    })
  })

  it('rejects invalid zones, reversed dates and incomplete platforms', () => {
    const form = emptyScheduleForm()
    form.timezone = 'Eastern'
    form.startDate = '2026-10-25'
    form.endDate = '2026-10-12'
    form.platforms.x = { include: true, weekdays: [], times: [], maxPerDay: '0', minGapHours: '' }
    form.staggerMinutes = '0'
    const result = buildScheduleInputs(form)
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.errors).toEqual([
        '“Eastern” is not a timezone this browser recognises.',
        'The end date is before the start date.',
        'x: choose at least one weekday.',
        'x: add at least one time.',
        'x: max posts per day must be a whole number ≥ 1.',
        'x: minimum gap must be a number of hours ≥ 0.',
      ])
    }
  })

  it('merges edits into a copy of the inputs', () => {
    const inputs = draftResponse().draft.inputs
    const next = withEdit(inputs, 'k', { remove: true })
    expect(next.edits).toEqual({ k: { remove: true } })
    expect(inputs.edits).toEqual({})
  })
})

describe('draft grouping', () => {
  it('nests companions under their parent and groups by local day', () => {
    const draft = draftResponse().draft
    const days = groupDraftJobs(draft.jobs, 'America/New_York')
    expect(days).toHaveLength(1)
    expect(days[0]?.dateKey).toBe('2026-10-12')
    expect(days[0]?.items).toHaveLength(1)
    expect(days[0]?.items[0]?.job.kind).toBe('post')
    expect(days[0]?.items[0]?.companions.map((c) => c.kind)).toEqual(['comment'])
    expect(fillSummary(draft)).toBe('1 of 2 requested slots fillable')
    expect(fillSummary({ summary: { requested: 24, filled: 18 } })).toBe('18 of 24 requested slots fillable')
  })
})
