import { describe, expect, it } from 'vitest'
import { realCatalog } from '../test/catalog'
import { bedsFor, catalogFormats, catalogGames, catalogMix, formatRenderable, mixLabel, projectsInOrder, stylesFor } from './catalog'

describe('catalog lookups', () => {
  const catalog = realCatalog()

  it('derives the games and formats the UI used to hardcode', () => {
    expect(catalogGames(catalog)).toEqual(['scalar', 'continuum', 'whenabouts', 'tectonic'])
    expect(catalogFormats(catalog, 'scalargame')).toEqual([
      'progressive-clues', 'candidate-elimination', 'head-to-head', 'missing-slot',
      'guess-the-year', 'before-after', 'missing-country', 'neighbor-clues',
    ])
    expect(catalogFormats(catalog, 'originals')).toEqual(['movie-recap', 'story-recap', 'animated-short'])
    expect(projectsInOrder(catalog).map((p) => p.id)).toEqual(['originals', 'scalargame'])
  })

  it('offers only live beds of the right game and length, and one style per game', () => {
    const beds = bedsFor(catalog, 'scalargame', 'head-to-head')
    expect(beds.length).toBeGreaterThan(0)
    expect(beds.every((b) => !b.retired && b.game === 'continuum' && b.durationSeconds === 20)).toBe(true)
    expect(bedsFor(catalog, 'scalargame', 'missing-slot').every((b) => b.durationSeconds === 22)).toBe(true)
    expect(bedsFor(catalog, 'originals', 'movie-recap')).toEqual([])
    expect(stylesFor(catalog, 'scalar').map((s) => s.id)).toEqual(['scalar-notebook-1'])
  })

  it('knows which formats an engine can render', () => {
    for (const project of catalog.projects) for (const format of project.formats) expect(formatRenderable(catalog, format)).toBe(true)
    expect(formatRenderable(catalog, { id: 'nope', name: 'Nope', engine: 'motion', route: null })).toBe(false)
    expect(formatRenderable(catalog, { id: 'movie-recap', name: 'x', engine: 'story', route: 'series' })).toBe(false)
    expect(formatRenderable(catalog, { id: 'x', name: 'x', engine: 'nope', route: null })).toBe(false)
  })
})

describe('mix targets', () => {
  it('has no mix while every target is null; a project without a target gets 0 once any is set', () => {
    const catalog = realCatalog()
    expect(catalogMix(catalog)).toBeNull()
    const set = { ...catalog, projects: catalog.projects.map((p) => ({ ...p, mix: { ...p.mix, target: p.id === 'scalargame' ? 0.8 : null } })) }
    expect(catalogMix(set)).toEqual({ originals: 0, scalargame: 0.8 })
    expect(mixLabel({ scalargame: 0.75, originals: 0.25 })).toBe('scalargame 75% · originals 25%')
  })
})
