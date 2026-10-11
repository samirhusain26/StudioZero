import { describe, expect, it } from 'vitest'
import type { FeedbackItem, NextBatchInfo } from '../api/types'
import { FEEDBACK_TAGS } from '../api/types'
import { buildBriefTemplate, buildCopyPrompt, buildFeedbackExport, feedbackFileName, feedbackJson, groupFeedback, TAG_LABELS } from './nextBatch'

const item = (over: Partial<FeedbackItem>): FeedbackItem => ({
  episodeId: 'scalar-clues-001',
  revision: 1,
  tags: [],
  note: '',
  status: 'open',
  updatedAt: '2026-10-15T10:00:00Z',
  batchId: '2026-10-b01',
  questionId: 'scalar:BOL:clues',
  game: 'scalar',
  format: 'progressive-clues',
  styleId: 'scalar-v1',
  ...over,
})

const info = (over: Partial<NextBatchInfo> = {}): NextBatchInfo => ({
  nextBatchId: '2026-11-b02',
  openFeedback: [
    item({ tags: ['great-reveal', 'music'], note: 'Loved the\nending.' }),
    item({ episodeId: 'tectonic-neighbors-003', game: 'tectonic', format: 'neighbor-clues', styleId: 'tectonic-v1', tags: ['hook-weak', 'too-easy'], note: 'Hook gives it away' }),
    item({ episodeId: 'whenabouts-year-002', batchId: '2026-10-pilots', game: 'whenabouts', format: 'guess-the-year', styleId: 'wa-v1', tags: ['drop'] }),
    item({ episodeId: 'continuum-h2h-004', game: 'continuum', format: 'head-to-head', styleId: 'c-v1', tags: [], note: 'Numbers too small on phone' }),
  ],
  lastBrief: null,
  lastRetro: { batchId: '2026-10-b01', kind: 'retro', text: '# Retro\nGood.', sha256: 'c'.repeat(64), bytes: 14, uploadedAt: '2026-10-18T09:00:00Z' },
  performance: [{ platform: 'instagram', status: 'confirmed', at: '2026-10-12T13:00:05Z', permalink: 'https://instagram.com/p/x', metrics: { checkpoint: '24h', fetchedAt: '2026-10-13T13:20:00Z', status: 'ok', values: { views: 1500 } } }],
  accounts: [{ platform: 'instagram', followers: 120, followersChange: 20, days: 7, totals: { impressions: 6300, engagements: 315, engagement_rate: 0.05 }, status: 'ok' }],
  funnel: [],
  tags: [...FEEDBACK_TAGS],
  ...over,
})

describe('TAG_LABELS', () => {
  it('has a human label for every contract tag', () => {
    expect(Object.keys(TAG_LABELS).sort()).toEqual([...FEEDBACK_TAGS].sort())
  })
})

describe('buildBriefTemplate', () => {
  it('has every section, prefilled from feedback and the last retro', () => {
    const brief = buildBriefTemplate(info())
    const headings = brief.split('\n').filter((l) => l.startsWith('#'))
    expect(headings).toEqual(['# Brief: 2026-11-b02', '## Goals', '## Mix', '## What worked', '## What to fix', '## Avoid', '## Experiments', '## Last retro'])
    expect(brief).toContain('Batch id: 2026-11-b02')
    expect(brief).toContain('- Games: <choose from scalar, continuum, whenabouts, tectonic>')
    const section = (name: string) => (brief.split(`## ${name}\n`)[1]?.split('\n\n')[0] ?? '').trimEnd()
    expect(section('What worked')).toBe('- scalar-clues-001 rev 1 (scalar / progressive-clues / scalar-v1): Great reveal — Loved the ending.')
    expect(section('What to fix')).toBe(
      [
        '- scalar-clues-001 rev 1 (scalar / progressive-clues / scalar-v1): Music — Loved the ending.',
        '- tectonic-neighbors-003 rev 1 (tectonic / neighbor-clues / tectonic-v1): Weak hook, Too easy — Hook gives it away',
        '- continuum-h2h-004 rev 1 (continuum / head-to-head / c-v1) — Numbers too small on phone',
      ].join('\n'),
    )
    expect(section('Avoid')).toBe('- whenabouts-year-002 rev 1 (whenabouts / guess-the-year / wa-v1): Drop')
    expect(section('Last retro')).toBe('- library/_retros/2026-10-b01.md (uploaded to the Pi 2026-10-18)')
  })

  it('explains empty sections instead of leaving them blank', () => {
    const brief = buildBriefTemplate(info({ openFeedback: [], lastRetro: null }))
    expect(brief).toContain('## What worked\n- No “keep” or “great reveal” feedback yet.')
    expect(brief).toContain('## What to fix\n- No fixes requested.')
    expect(brief).toContain('## Avoid\n- Nothing marked “drop”.')
    expect(brief).toContain('## Last retro\n- No retro uploaded yet.')
  })
})

describe('buildCopyPrompt', () => {
  it('is exactly the §3 hand-off text', () => {
    expect(buildCopyPrompt('2026-11-b02', '# Brief\n\nGoals')).toBe(
      '/video-batch brief 2026-11-b02\n\n# Brief\n\nGoals\n\nFeedback file: library/_inbox/feedback-2026-11-b02.json',
    )
  })
})

describe('buildFeedbackExport', () => {
  it('matches the §3 schema exactly', () => {
    const doc = buildFeedbackExport({ info: info(), brief: 'B', fromCommit: 'f'.repeat(40), exportedAt: new Date('2026-11-02T18:00:00.123Z') })
    expect(Object.keys(doc)).toEqual(['schemaVersion', 'kind', 'exportedAt', 'fromCommit', 'nextBatchId', 'brief', 'lastRetro', 'feedback', 'performance', 'accounts'])
    expect(doc).toMatchObject({
      schemaVersion: 1,
      kind: 'scalar-next-batch-feedback',
      exportedAt: '2026-11-02T18:00:00Z',
      fromCommit: 'f'.repeat(40),
      nextBatchId: '2026-11-b02',
      brief: 'B',
      lastRetro: { batchId: '2026-10-b01', text: '# Retro\nGood.' },
      performance: [{ platform: 'instagram', status: 'confirmed', at: '2026-10-12T13:00:05Z', permalink: 'https://instagram.com/p/x', metrics: { checkpoint: '24h', fetchedAt: '2026-10-13T13:20:00Z', status: 'ok', values: { views: 1500 } } }],
      accounts: [{ platform: 'instagram', followers: 120, followersChange: 20, days: 7, totals: { impressions: 6300, engagements: 315, engagement_rate: 0.05 }, status: 'ok' }],
    })
    expect(Object.keys(doc.lastRetro ?? {})).toEqual(['batchId', 'text'])
    expect(Object.keys(doc.feedback[0] ?? {})).toEqual(['episodeId', 'revision', 'batchId', 'questionId', 'game', 'format', 'styleId', 'tags', 'note', 'updatedAt'])
    expect(doc.feedback[1]).toEqual({
      episodeId: 'tectonic-neighbors-003', revision: 1, batchId: '2026-10-b01', questionId: 'scalar:BOL:clues', game: 'tectonic',
      format: 'neighbor-clues', styleId: 'tectonic-v1', tags: ['hook-weak', 'too-easy'], note: 'Hook gives it away', updatedAt: '2026-10-15T10:00:00Z',
    })
  })

  it('uses null for a missing retro and commit, and serialises with a trailing newline', () => {
    const doc = buildFeedbackExport({ info: info({ lastRetro: null, openFeedback: [], performance: [] }), brief: '', fromCommit: null, exportedAt: new Date('2026-11-02T18:00:00Z') })
    expect(doc.lastRetro).toBeNull()
    expect(doc.fromCommit).toBeNull()
    const text = feedbackJson(doc)
    expect(text.endsWith('}\n')).toBe(true)
    expect(JSON.parse(text)).toEqual(doc)
    expect(feedbackFileName('2026-11-b02')).toBe('feedback-2026-11-b02.json')
  })
})

describe('groupFeedback', () => {
  it('groups by batch (ids descending) and sorts episodes', () => {
    const groups = groupFeedback(info().openFeedback)
    expect(groups.map((g) => g.batchId)).toEqual(['2026-10-pilots', '2026-10-b01'])
    expect(groups[1]?.items.map((i) => i.episodeId)).toEqual(['continuum-h2h-004', 'scalar-clues-001', 'tectonic-neighbors-003'])
  })
})
