import { describe, expect, it } from 'vitest'
import { episodeHash, guideHash, routeFromHash, screenOf, VIEWS, viewFromHash } from './views'

describe('hash routes', () => {
  it('has the six sections in tab order', () => {
    expect(VIEWS.map((v) => v.label)).toEqual(['Home', 'Studio', 'Library', 'Schedule', 'Activity', 'Settings'])
  })

  it('parses section hashes, defaulting to Home', () => {
    expect(viewFromHash('#/library')).toBe('library')
    expect(viewFromHash('#/settings')).toBe('settings')
    expect(viewFromHash('#/home')).toBe('home')
    expect(viewFromHash('')).toBe('home')
    expect(viewFromHash('#/nope')).toBe('home')
    expect(routeFromHash('#main')).toEqual({ view: 'home' })
  })

  it('redirects every old hash to its new place', () => {
    expect(routeFromHash('#/dashboard')).toEqual({ view: 'home', redirect: '#/home' })
    expect(routeFromHash('#/history')).toEqual({ view: 'activity', tab: 'posts', redirect: '#/activity?tab=posts' })
    expect(routeFromHash('#/activation')).toEqual({ view: 'settings', section: 'activation', redirect: '#/settings#activation' })
    expect(routeFromHash('#/next-batch')).toEqual({ view: 'studio', make: true, redirect: '#/studio/make' })
    expect(routeFromHash('#/library/make')).toEqual({ view: 'studio', make: true, redirect: '#/studio/make' })
    // The redirect targets parse to the same routes without a further redirect.
    for (const old of ['#/dashboard', '#/history', '#/activation', '#/next-batch', '#/library/make']) {
      const { redirect, ...route } = routeFromHash(old)
      expect(routeFromHash(redirect ?? '')).toEqual(route)
    }
  })

  it('parses sub-routes: make, activity posts tab, settings sections', () => {
    expect(routeFromHash('#/studio/make')).toEqual({ view: 'studio', make: true })
    expect(routeFromHash('#/studio/make?project=originals')).toEqual({ view: 'studio', make: true, project: 'originals' })
    expect(routeFromHash('#/studio/make?project=Bad<x>')).toEqual({ view: 'studio', make: true })
    expect(routeFromHash('#/studio')).toEqual({ view: 'studio' })
    expect(routeFromHash('#/studio/export')).toEqual({ view: 'studio', export: true })
    expect(screenOf(routeFromHash('#/studio/export'))).toBe('export')
    expect(routeFromHash('#/studio/jobs')).toEqual({ view: 'studio', jobs: true })
    expect(routeFromHash('#/studio/jobs/Galactic_Garage')).toEqual({ view: 'studio', job: 'Galactic_Garage' })
    expect(routeFromHash('#/studio/jobs/..%2Fetc')).toEqual({ view: 'studio', jobs: true })
    expect(routeFromHash('#/studio/renders')).toEqual({ view: 'studio', renders: true })
    expect(routeFromHash('#/studio/story-settings')).toEqual({ view: 'studio', storySettings: true })
    expect(['#/studio/jobs', '#/studio/jobs/A', '#/studio/renders', '#/studio/story-settings'].map((h) => screenOf(routeFromHash(h)))).toEqual(['jobs', 'job', 'renders', 'storySettings'])
    expect(routeFromHash('#/studio/nope')).toEqual({ view: 'studio' })
    expect(screenOf(routeFromHash('#/studio'))).toBe('studio')
    expect(routeFromHash('#/schedule/queue')).toEqual({ view: 'schedule', queue: true })
    expect(screenOf(routeFromHash('#/schedule/queue'))).toBe('queue')
    expect(routeFromHash('#/activity?tab=posts')).toEqual({ view: 'activity', tab: 'posts' })
    expect(routeFromHash('#/activity?tab=nope')).toEqual({ view: 'activity' })
    expect(routeFromHash('#/activity?tab=system')).toEqual({ view: 'activity', tab: 'system' })
    expect(routeFromHash('#/activity?tab=all')).toEqual({ view: 'activity' })
    expect(routeFromHash('#/settings#update')).toEqual({ view: 'settings', section: 'update' })
    expect(routeFromHash('#/settings#Bad<x>')).toEqual({ view: 'settings' })
    expect(routeFromHash('#/home#platforms')).toEqual({ view: 'home', section: 'platforms' })
    expect(screenOf(routeFromHash('#/studio/make'))).toBe('make')
    expect(screenOf(routeFromHash(episodeHash('a', 1)))).toBe('episode')
    expect(screenOf(routeFromHash('#/settings#update'))).toBe('settings')
  })

  it('parses episode detail routes, round-tripping odd ids', () => {
    expect(routeFromHash('#/library/episode/scalar-clues-001/2')).toEqual({ view: 'library', episode: { episodeId: 'scalar-clues-001', revision: 2 } })
    const hash = episodeHash('manual:ab/c d', 1)
    expect(hash).toBe('#/library/episode/manual%3Aab%2Fc%20d/1')
    expect(routeFromHash(hash)).toEqual({ view: 'library', episode: { episodeId: 'manual:ab/c d', revision: 1 } })
    expect(routeFromHash('#/library/episode/x/not-a-number')).toEqual({ view: 'library' })
    expect(routeFromHash('#/library/episode/%E0%A4%A/1')).toEqual({ view: 'library' })
  })

  it('parses guide anchors', () => {
    expect(routeFromHash(guideHash('update-the-pi'))).toEqual({ view: 'guide', anchor: 'update-the-pi' })
    expect(routeFromHash('#/guide')).toEqual({ view: 'guide' })
    expect(routeFromHash('#/guide/Bad<Anchor>')).toEqual({ view: 'guide' })
  })
})
