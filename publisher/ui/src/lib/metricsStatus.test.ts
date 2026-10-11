import { describe, expect, it } from 'vitest'
import { parseBackfill, platformRuns, triggerWords } from './metricsStatus'

describe('post stats wording', () => {
  it('accepts a whole number of days 0–93 for the backfill', () => {
    expect(parseBackfill('')).toBe(0)
    expect(parseBackfill(' 7 ')).toBe(7)
    expect(parseBackfill('93')).toBe(93)
    expect(parseBackfill('94')).toBeNull()
    expect(parseBackfill('-1')).toBeNull()
    expect(parseBackfill('2.5')).toBeNull()
  })

  it('says how a run was started', () => {
    const base = { startedAt: '', finishedAt: '', outcome: 'ok' as const, platforms: {} }
    expect(triggerWords({ ...base, trigger: 'timer', backfill: 0 })).toBe('by the hourly timer')
    expect(triggerWords({ ...base, trigger: 'request', backfill: 1 })).toBe('on request, also past 1 day')
  })

  it('lists platforms in a stable order', () => {
    const r = { status: 'ok' as const, postsRead: 0, accountsRead: 0, reason: null }
    const order = platformRuns({ startedAt: '', finishedAt: '', trigger: 'timer', backfill: 0, outcome: 'ok', platforms: { x: r, bluesky: r, instagram: r, youtube: r, zeta: r } })
    expect(order.map(([p]) => p)).toEqual(['instagram', 'youtube', 'bluesky', 'x', 'zeta'])
  })
})
