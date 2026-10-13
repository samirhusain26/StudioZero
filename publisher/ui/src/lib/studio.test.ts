import { describe, expect, it } from 'vitest'
import { realCatalog } from '../test/catalog'
import type { Runway } from './runway'
import { projectSummaries } from './studio'

const runway: Runway = {
  today: '2026-10-12', platforms: [], firstGap: '2026-10-20', firstGapPlatforms: [], lastDay: '2026-10-25',
  lastDayByGroup: { scalar: '2026-10-25', tectonic: '2026-10-24' },
}

describe('projectSummaries', () => {
  it('lists projects in order with budgets and mix stated, never invented', () => {
    const [originals, scalargame] = projectSummaries(realCatalog(), runway)
    expect(originals).toMatchObject({
      id: 'originals',
      priority: 'P0',
      engines: ['Story'],
      budget: '$0 a month · every paid run needs your OK with a cost estimate',
      mix: '0% of scheduled posts now · target share not set (your decision)',
      scheduledThrough: null,
      nextBatchBy: null,
      contract: 'contract v2',
    })
    expect(scalargame).toMatchObject({
      id: 'scalargame',
      engines: ['Motion'],
      budget: '$0 a month · no paid services',
      mix: '100% of scheduled posts now · target share not set (your decision)',
      scheduledThrough: '2026-10-25',
      nextBatchBy: '2026-10-18',
    })
    expect(scalargame?.formats.every((f) => f.renderable)).toBe(true)
  })

  it('says a set target and unknown runway', () => {
    const catalog = realCatalog()
    const p = catalog.projects.find((x) => x.id === 'scalargame')
    if (p) p.mix.target = 0.6
    expect(projectSummaries(catalog, undefined)[1]).toMatchObject({ mix: '100% of scheduled posts now · target 60%', scheduledThrough: undefined })
    expect(projectSummaries(catalog, null)[1]?.scheduledThrough).toBeNull()
  })

  it('counts each project by its own scheduled posts', () => {
    const both = { ...runway, lastDayByGroup: { ...runway.lastDayByGroup, originals: '2026-10-30' } }
    const [originals, scalargame] = projectSummaries(realCatalog(), both)
    expect([originals?.scheduledThrough, scalargame?.scheduledThrough]).toEqual(['2026-10-30', '2026-10-25'])
  })
})
