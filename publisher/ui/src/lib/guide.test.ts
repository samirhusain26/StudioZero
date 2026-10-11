import { describe, expect, it } from 'vitest'
import { buildGuide, GUIDE, hasAnchor } from './guide'
import { SCREEN_HELP, SETTINGS_SECTION_ANCHORS } from './help'
import { SCREEN_TITLES } from '../views'
import { linkTargets } from './markdown'

/** Required headings per file (REBUILD_CONTRACTS.md §4). */
const REQUIRED: Record<string, string[]> = {
  overview: ['how-it-works', 'where-things-live'],
  'make-a-batch': ['make-a-batch', 'brief', 'checkpoints', 'finalize', 'retro'],
  upload: ['upload-a-batch', 'batch-notes', 'failed-upload'],
  review: ['review-episodes', 'feedback', 'approve-content'],
  schedule: ['schedule', 'approve-a-schedule', 'activation'],
  'next-batch': ['next-batch'],
  update: ['update-the-pi', 'failed-update', 'rollback', 'unit-files-changed'],
  health: ['health', 'recovery'],
  'owner-only': ['things-only-samir-can-do'],
  glossary: ['glossary'],
}

describe('bundled guide', () => {
  it('has every guide file with its required anchors', () => {
    for (const [doc, anchors] of Object.entries(REQUIRED)) {
      const own = GUIDE.headings.filter((h) => h.doc === doc).map((h) => h.anchor)
      for (const anchor of anchors) expect(own, `${doc}.md must have a heading for #${anchor}`).toContain(anchor)
    }
  })

  it('has every per-screen help anchor', () => {
    for (const [screen, help] of Object.entries(SCREEN_HELP)) {
      expect(hasAnchor(GUIDE, help.anchor), `${screen} links to #${help.anchor}`).toBe(true)
      expect(help.lines.length).toBeGreaterThanOrEqual(2)
      expect(help.lines.length).toBeLessThanOrEqual(4)
    }
  })

  it('maps every screen to an existing anchor for the help icon (meta.json screens)', () => {
    for (const screen of Object.keys(SCREEN_TITLES)) {
      const anchor = GUIDE.meta.screens[screen]
      expect(anchor, `meta.json screens.${screen}`).toBeTruthy()
      expect(hasAnchor(GUIDE, anchor ?? ''), `help icon on ${screen} links to #${anchor}`).toBe(true)
    }
    for (const [section, anchor] of Object.entries(SETTINGS_SECTION_ANCHORS)) {
      expect(hasAnchor(GUIDE, anchor), `help icon on Settings › ${section} links to #${anchor}`).toBe(true)
    }
  })

  it('resolves every in-guide #anchor link', () => {
    for (const doc of GUIDE.docs) {
      for (const target of linkTargets(doc.blocks).filter((t) => t.startsWith('#'))) {
        expect(hasAnchor(GUIDE, target.slice(1)), `${doc.name}.md links to ${target}`).toBe(true)
      }
    }
  })

  it('reads meta.json and follows its order', () => {
    expect(GUIDE.meta.updated).toMatch(/^\d{4}-\d{2}-\d{2}$/)
    const listed = GUIDE.meta.order.filter((n) => GUIDE.docs.some((d) => d.name === n))
    expect(GUIDE.docs.slice(0, listed.length).map((d) => d.name)).toEqual(listed)
  })

  it('orders docs by meta, then unlisted files alphabetically', () => {
    const guide = buildGuide(
      { '/g/b.md': '# B', '/g/a.md': '# A', '/g/z.md': '# Z' },
      JSON.stringify({ updated: '2026-10-08', order: ['z', 'missing'] }),
    )
    expect(guide.docs.map((d) => d.name)).toEqual(['z', 'a', 'b'])
    expect(buildGuide({ '/g/a.md': '# A' }, 'not json').meta).toEqual({ updated: 'unknown', order: ['a'], screens: {} })
  })
})
