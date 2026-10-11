import { describe, expect, it } from 'vitest'
import type { ChannelSummary, LibraryEpisode, Platform, QueueJob, ScheduleResponse } from '../api/types'
import { calendarMonths, computeRunway } from './runway'

const channel = (platform: Platform, blockedReason: string | null = null): ChannelSummary => ({
  platform, accountId: 'acct', route: 'buffer', enabled: true, identityVerified: true, publishingVerified: true, blockedReason, profileUrl: null,
})

const job = (over: Partial<QueueJob>): QueueJob =>
  ({
    key: over.key ?? Math.random().toString(36), jobId: null, platform: 'threads', accountId: 'acct', slotUtc: '2026-10-10T13:00:00Z', kind: 'post',
    episodeKey: 'e', parentKey: null, episodeId: 'ep', questionId: 'q1', game: 'scalar', text: 't', youtube: null, coverUrl: null,
    status: 'not-enqueued', statusLabel: '', dispatched: false, editable: true, lockReason: null, permalink: null, error: null, ...over,
  }) as QueueJob

const episode = (questionId: string, over: Partial<LibraryEpisode> = {}): LibraryEpisode =>
  ({
    episodeId: questionId, revision: 1, questionId, status: 'approved', currentApproval: { id: 1 },
    platforms: { threads: { eligible: true, reason: null }, x: { eligible: true, reason: null } }, postedOn: [], ...over,
  }) as unknown as LibraryEpisode

const schedule = (jobs: QueueJob[], channels = [channel('threads'), channel('x'), channel('tiktok', 'Not connected')]): ScheduleResponse => ({
  displayTimezone: 'America/New_York',
  manifest: { sha256: 'a'.repeat(64), draftSha256: 'b'.repeat(64), approvedAt: '2026-10-08T00:00:00Z', scope: ['threads', 'x'], bound: true, jobCount: jobs.length },
  jobs, pendingRequest: null, lastResult: null, channels, recentDrafts: [],
})

const now = new Date('2026-10-09T16:00:00Z') // Fri 9 Oct, 12:00 EDT

describe('computeRunway', () => {
  it('reports the last scheduled day per platform and the first day a platform runs dry', () => {
    const r = computeRunway(
      schedule([
        job({ slotUtc: '2026-10-10T13:00:00Z', questionId: 'q1' }),
        job({ slotUtc: '2026-10-12T13:00:00Z', questionId: 'q2' }),
        job({ platform: 'x', slotUtc: '2026-10-10T13:30:00Z', questionId: 'q1' }),
        job({ platform: 'x', slotUtc: '2026-10-11T13:30:00Z', questionId: 'q2', status: 'failed' }),
        job({ kind: 'comment', slotUtc: '2026-10-20T13:00:00Z' }),
      ]),
      null,
      now,
    )
    expect(r.today).toBe('2026-10-09')
    expect(r.platforms.map((p) => p.platform)).toEqual(['threads', 'x'])
    expect(r.platforms[0]).toMatchObject({ scheduledThrough: '2026-10-12', postsLeft: 2, spare: null, couldReach: null })
    // The failed X post does not cover its day.
    expect(r.platforms[1]).toMatchObject({ scheduledThrough: '2026-10-10', postsLeft: 1 })
    expect(r.firstGap).toBe('2026-10-11')
    expect(r.firstGapPlatforms).toEqual(['x'])
    expect(r.lastDay).toBe('2026-10-12')
  })

  it('counts approved, eligible, unused questions once and extends from the end of the queue', () => {
    const episodes = [
      episode('q1'), // queued on threads
      episode('q2'),
      episode('q2', { episodeId: 'q2-variant' }), // same question: counted once
      episode('q3', { postedOn: [{ platform: 'threads', accountId: 'acct', status: 'confirmed', slotUtc: '2026-10-01T13:00:00Z' }] }),
      episode('q4', { status: 'reviewable', currentApproval: null }),
      episode('q5', { platforms: { threads: { eligible: false, reason: 'too long' }, x: { eligible: true, reason: null } } as LibraryEpisode['platforms'] }),
    ]
    const r = computeRunway(schedule([job({ slotUtc: '2026-10-12T13:00:00Z', questionId: 'q1' })]), episodes, now)
    const threads = r.platforms.find((p) => p.platform === 'threads')
    expect(threads?.spare).toBe(1) // q2 only
    expect(threads?.couldReach).toBe('2026-10-13')
    const x = r.platforms.find((p) => p.platform === 'x')
    expect(x).toMatchObject({ scheduledThrough: null, spare: 4, couldReach: '2026-10-12' }) // q1, q2, q3, q5 from today
    expect(r.firstGap).toBe('2026-10-09')
  })

  it('with no manifest uses the schedulable channels only', () => {
    const r = computeRunway({ ...schedule([]), manifest: null }, [], now)
    expect(r.platforms.map((p) => p.platform)).toEqual(['threads', 'x'])
    expect(r.lastDay).toBeNull()
    expect(r.platforms.every((p) => p.spare === 0 && p.couldReach === null)).toBe(true)
  })
})

describe('calendarMonths', () => {
  it('builds Monday-first weeks across months and places posts on their local day', () => {
    const months = calendarMonths(
      [job({ slotUtc: '2026-10-31T03:00:00Z', key: 'late' }), job({ kind: 'comment', slotUtc: '2026-10-12T13:00:00Z' })],
      'America/New_York',
      '2026-10-09',
      '2026-11-02',
    )
    expect(months.map((m) => m.key)).toEqual(['2026-10', '2026-11'])
    const oct = months[0]
    expect(oct?.weeks[0]?.[0]).toMatchObject({ dateKey: '2026-09-28', inMonth: false })
    expect(oct?.weeks.every((w) => w.length === 7)).toBe(true)
    // 03:00 UTC on the 31st is the evening of the 30th in New York; the comment is not a post.
    const days = oct?.weeks.flat() ?? []
    expect(days.find((d) => d.dateKey === '2026-10-30')?.posts.map((p) => p.key)).toEqual(['late'])
    expect(days.find((d) => d.dateKey === '2026-10-12')?.posts).toEqual([])
  })
})
