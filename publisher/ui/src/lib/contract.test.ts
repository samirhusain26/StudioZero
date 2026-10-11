import { describe, expect, it } from 'vitest'
import { CAPTION_LIMITS, captionCounter, captionIssues, codePoints, counter, estimatedManualEpisodeId, linkFor, textLength, utf8Bytes } from './contract'

const link = { deepLink: '/scalar', utmCampaign: 'social_manual_v1', episodeId: 'scalar-manual-001' }

describe('character counting', () => {
  it('counts code points like Python len()', () => {
    expect(codePoints('abc')).toBe(3)
    expect('🌍'.length).toBe(2)
    expect(codePoints('🌍 quiz')).toBe(6)
  })

  it('weighs X URLs as 23 characters', () => {
    expect(textLength('x', 'Play https://www.scalargame.com/scalar?utm_source=x now')).toBe('Play  now'.length + 23)
    expect(textLength('threads', 'Play https://a.example now')).toBe('Play https://a.example now'.length)
  })

  it('counts UTF-8 bytes for YouTube descriptions', () => {
    expect(utf8Bytes('é')).toBe(2)
    expect(utf8Bytes('abc')).toBe(3)
  })

  it('expands {link} the way the Pi does', () => {
    const expanded = linkFor('/scalar', 'social_manual_v1', 'threads', 'scalar-manual-001')
    expect(expanded).toBe(
      'https://www.scalargame.com/scalar?utm_source=threads&utm_medium=organic_social&utm_campaign=social_manual_v1&utm_content=scalar-manual-001',
    )
    expect(captionCounter('threads', 'Go {link}', CAPTION_LIMITS.threads, link).length).toBe(3 + expanded.length)
    expect(captionCounter('x', 'Go {link}', CAPTION_LIMITS.x, link).length).toBe(3 + 23)
  })

  it('estimates the manual episode id the Pi assigns', () => {
    expect(estimatedManualEpisodeId('tectonic', new Date('2026-10-06T23:30:00Z'))).toBe('tectonic-manual-20261006-001')
  })
})

describe('limits', () => {
  it('reports remaining and over-limit labels', () => {
    expect(counter(212, 280)).toMatchObject({ over: false, remaining: 68, label: '212 / 280' })
    expect(counter(285, 280)).toMatchObject({ over: true, remaining: -5, label: '5 over the 280 limit' })
    expect(counter(280, 280).over).toBe(false)
  })

  it('mirrors library_contract caption limits', () => {
    expect(CAPTION_LIMITS).toEqual({ instagram: 2200, facebook: 2200, threads: 500, x: 280, bluesky: 300, tiktok: 2200 })
    const long = 'a'.repeat(301)
    expect(captionCounter('bluesky', long, CAPTION_LIMITS.bluesky, link).over).toBe(true)
  })

  it('flags {link} where links are not clickable and unknown placeholders', () => {
    expect(captionIssues('instagram', 'Play {link}')).toEqual(['This platform does not show clickable links; remove {link}.'])
    expect(captionIssues('threads', 'Play {link}')).toEqual([])
    expect(captionIssues('x', 'Hi {name}')).toEqual(['Only {link} is expanded; remove other {…} placeholders.'])
  })
})
