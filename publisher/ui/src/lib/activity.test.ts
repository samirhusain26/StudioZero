import { describe, expect, it } from 'vitest'
import type { ActivityEntry } from '../api/types'
import { groupByDay, mergeHead } from './activity'

function entry(at: string, n: number): ActivityEntry {
  return {
    id: `${at}|j:${String(n).padStart(12, '0')}`,
    at,
    kind: 'job',
    event: 'job.confirmed',
    severity: 'success',
    title: 'Posted on Instagram',
    detail: null,
    platform: 'instagram',
    accountId: '111',
    jobId: null,
    episode: null,
    episodeId: null,
    game: null,
    jobKind: null,
    permalink: null,
    draftSha256: null,
    manifestSha256: null,
    batchId: null,
  }
}

describe('groupByDay', () => {
  it('groups by local day in the display zone', () => {
    const days = groupByDay(
      [entry('2026-10-07T03:30:00Z', 3), entry('2026-10-06T22:00:00Z', 2), entry('2026-10-06T03:00:00Z', 1)],
      'America/New_York',
    )
    expect(days.map((d) => [d.dateKey, d.entries.length])).toEqual([
      ['2026-10-06', 2],
      ['2026-10-05', 1],
    ])
  })
})

describe('mergeHead', () => {
  it('keeps the fresh head and older pages below it without duplicates', () => {
    const a = entry('2026-10-07T10:00:00Z', 4)
    const b = entry('2026-10-07T09:00:00Z', 3)
    const c = entry('2026-10-07T08:00:00Z', 2)
    const d = entry('2026-10-07T07:00:00Z', 1)
    expect(mergeHead([a, b], [b, c, d], false).map((e) => e.id)).toEqual([a.id, b.id, c.id, d.id])
    expect(mergeHead([a, b], [c, d], true).map((e) => e.id)).toEqual([a.id, b.id])
  })
})
