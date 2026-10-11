import { describe, expect, it } from 'vitest'
import type { ActivityEntry } from '../api/types'
import { feedQuery, isActivityTab, matchesSearch, menuFilterCount, NO_FILTERS, postsQuery } from './activityFilters'

const entry: ActivityEntry = {
  id: '2026-10-07T13:00:00Z|j:1', at: '2026-10-07T13:00:00Z', kind: 'job', event: 'job.confirmed', severity: 'success',
  title: 'Published on Threads', detail: 'Confirmed.', platform: 'threads', accountId: 't-1', jobId: 'abc123def456',
  episode: 'scalar:Q2:clues', episodeId: 'scalar-clues-002', game: 'scalar', jobKind: 'post', permalink: null,
  draftSha256: null, manifestSha256: null, batchId: null,
}

describe('activity filters', () => {
  it('maps chips to activity kinds and only sends chosen filters', () => {
    expect(feedQuery('all', NO_FILTERS)).toEqual({})
    expect(feedQuery('uploads', NO_FILTERS)).toEqual({ kind: 'library' })
    expect(feedQuery('approvals', { ...NO_FILTERS, platform: 'x', status: 'failed' })).toEqual({ kind: 'approval', platform: 'x' })
    expect(feedQuery('system', { ...NO_FILTERS, severity: 'error' })).toEqual({ kind: 'system', severity: 'error' })
  })

  it('maps Posts to the old History query (search runs on the Pi)', () => {
    expect(postsQuery(NO_FILTERS)).toEqual({})
    expect(postsQuery({ ...NO_FILTERS, q: '  scalar:Q2 ', platform: 'threads', status: 'confirmed', from: '2026-10-01', to: '2026-10-07', severity: 'error' }))
      .toEqual({ q: 'scalar:Q2', platform: 'threads', status: 'confirmed', from: '2026-10-01', to: '2026-10-07' })
  })

  it('counts only the menu filters that apply to the tab', () => {
    const f = { ...NO_FILTERS, q: 'x', platform: 'x' as const, severity: 'error' as const, status: 'failed' as const, from: '2026-10-01' }
    expect(menuFilterCount('all', f)).toBe(2)
    expect(menuFilterCount('posts', f)).toBe(3)
    expect(menuFilterCount('posts', NO_FILTERS)).toBe(0)
  })

  it('searches loaded entries by every word, ids included', () => {
    expect(matchesSearch(entry, '')).toBe(true)
    expect(matchesSearch(entry, 'threads Q2')).toBe(true)
    expect(matchesSearch(entry, 'abc123')).toBe(true)
    expect(matchesSearch(entry, 'instagram')).toBe(false)
  })

  it('knows its tabs', () => {
    expect(isActivityTab('posts')).toBe(true)
    expect(isActivityTab('history')).toBe(false)
    expect(isActivityTab(undefined)).toBe(false)
  })
})
