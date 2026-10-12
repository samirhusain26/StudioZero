import { describe, expect, it } from 'vitest'
import type { EpisodeFunnel, FunnelLabels } from '../api/types'
import { groupFunnel } from './funnel'

const counted = { views: [], engaged: [], answered: [], avgWatchSeconds: [], followsThatDay: [] }
const labels = (over: Partial<FunnelLabels> = {}): FunnelLabels => ({
  project: 'scalargame', engine: 'motion', route: null, format: 'progressive-clues', renderer: null, group: 'scalar', ...over,
})
const row = (episode: string, views: number | null, engaged: number | null, l: FunnelLabels | null): EpisodeFunnel => ({
  episode, labels: l, publishedDates: [], views, engaged, answered: null, avgWatchSeconds: null, followsThatDay: null, counted, platforms: {},
})

describe('Learn grouping', () => {
  const rows = [
    row('scalar:a', 1000, 50, labels()),
    row('scalar:b', 500, null, labels({ renderer: 'web', format: 'head-to-head' })),
    row('originals:movie-recap:x', 3000, 300, labels({ project: 'originals', engine: 'story', route: 'recap', format: 'movie-recap', group: 'originals' })),
    row('ep01', null, null, null),
  ]

  it('adds up views and engaged by project, never turning "no data" into zero', () => {
    expect(groupFunnel(rows, 'project')).toEqual([
      { key: 'originals', videos: 1, views: 3000, engaged: 300, answered: null, engagedRate: 10 },
      { key: 'scalargame', videos: 2, views: 1500, engaged: 50, answered: null, engagedRate: 5 },
      { key: 'Not in the library', videos: 1, views: null, engaged: null, answered: null, engagedRate: null },
    ])
  })

  it('groups by engine, format and renderer', () => {
    expect(groupFunnel(rows, 'engine').map((g) => g.key)).toEqual(['story · recap', 'motion', 'Not in the library'])
    expect(groupFunnel(rows, 'format').map((g) => [g.key, g.videos])).toEqual([['movie-recap', 1], ['progressive-clues', 1], ['head-to-head', 1], ['Not in the library', 1]])
    expect(groupFunnel(rows, 'renderer').map((g) => g.key)).toEqual(['Not recorded', 'Browser export', 'Not in the library'])
  })
})
