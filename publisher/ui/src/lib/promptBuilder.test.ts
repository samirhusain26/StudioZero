import { describe, expect, it } from 'vitest'
import type { FeedbackItem } from '../api/types'
import { realCatalog } from '../test/catalog'
import { bedsFor } from './catalog'
import {
  applyPreset,
  buildPlanBrief,
  buildPlanPrompt,
  CALM,
  defaultPlan,
  deletePreset,
  evenMix,
  MAX_PRESETS,
  planProblems,
  plansGeneratedVideo,
  PRESETS_KEY,
  readPresets,
  savePreset,
  storyVideoModels,
  totalEpisodes,
  type BatchPlan,
} from './promptBuilder'
import { SAFETY_LINES } from './promptSafety'

const catalog = realCatalog()
const SAFETY = SAFETY_LINES.join('\n')

function memoryStorage(initial: Record<string, string> = {}): Storage {
  const data = new Map(Object.entries(initial))
  return {
    get length() {
      return data.size
    },
    key: (i: number) => [...data.keys()][i] ?? null,
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
    removeItem: (k: string) => void data.delete(k),
    clear: () => data.clear(),
  }
}

const blocked: Storage = {
  length: 0,
  key: () => null,
  getItem: () => {
    throw new Error('blocked')
  },
  setItem: () => {
    throw new Error('blocked')
  },
  removeItem: () => {
    throw new Error('blocked')
  },
  clear: () => undefined,
}

const feedback: FeedbackItem = {
  episodeId: 'scalar-clues-001',
  revision: 1,
  tags: ['great-reveal'],
  note: 'Loved it',
  status: 'open',
  updatedAt: '2026-10-15T10:00:00Z',
  batchId: '2026-10-b01',
  questionId: 'scalar:BOL:clues',
  game: 'scalar',
  format: 'progressive-clues',
  styleId: 'scalar-notebook-1',
}

function scalar(over: Partial<BatchPlan> = {}): BatchPlan {
  return { ...defaultPlan(catalog, 'scalargame', '2026-11-b02'), ...over }
}

describe('evenMix', () => {
  it('splits episodes over the difficulties, easier first', () => {
    expect([0, 1, 2, 3, 4, 5].map(evenMix)).toEqual([[0, 0, 0], [1, 0, 0], [1, 1, 0], [1, 1, 1], [2, 1, 1], [2, 2, 1]])
  })
})

describe('defaultPlan', () => {
  it('offers every Scalargame format with a style per game and the calm beds', () => {
    const plan = scalar()
    expect(plan.scope).toHaveLength(8)
    expect(totalEpisodes(plan)).toBe(24)
    expect(plan.styles).toEqual({
      scalar: 'scalar-notebook-1',
      continuum: 'continuum-poster-1',
      whenabouts: 'whenabouts-almanac-1',
      tectonic: 'tectonic-ocean-1',
    })
    expect(Object.values(plan.music).every((m) => m === CALM)).toBe(true)
    expect(planProblems(catalog, plan)).toEqual([])
  })

  it('starts Originals with one episode of its first format and no subject', () => {
    const plan = defaultPlan(catalog, 'originals', '2026-11-originals-01')
    expect(plan.scope.map((r) => [r.format, r.count])).toEqual([['movie-recap', 1], ['story-recap', 0], ['animated-short', 0]])
    expect(planProblems(catalog, plan)).toEqual(['Name at least one subject (a title or story idea per line).'])
  })
})

describe('planProblems', () => {
  it('refuses anything the catalog does not offer', () => {
    const plan = scalar({
      batchId: 'b02',
      scope: [
        { format: 'progressive-clues', count: 2, mix: [1, 1, 1] },
        { format: 'made-up', count: 1, mix: [1, 0, 0] },
        { format: 'head-to-head', count: 31, mix: [31, 0, 0] },
      ],
      styles: { scalar: 'continuum-poster-1' },
      music: { 'progressive-clues': 'continuum-20-holizna-clouds' },
      experimentId: 'Bad Id',
      spares: 9,
    })
    expect(planProblems(catalog, plan)).toEqual([
      'Batch id must look like YYYY-MM-name (lowercase letters, digits, dashes).',
      'Progressive clues: the difficulty mix must add up to 2.',
      'Format “made-up” is not in the Scalargame catalog.',
      'Head to head: episodes must be a whole number from 0 to 30.',
      'Spares must be a whole number from 0 to 5.',
      'Choose a style for scalar.',
      'Choose a style for continuum.',
      'Music for progressive-clues: choose the calm rotation or a bed of the right game and length.',
      'Music for head-to-head: choose the calm rotation or a bed of the right game and length.',
      'Experiment id: lowercase letters, digits and dashes (up to 64).',
    ])
  })

  it('refuses retired beds and beds of the wrong length', () => {
    const retired = catalog.engines[0]?.beds?.find((b) => b.retired && b.game === 'continuum' && b.durationSeconds === 20)
    expect(retired).toBeDefined()
    const plan = scalar({ music: { ...scalar().music, 'head-to-head': retired?.id ?? '', 'missing-slot': bedsFor(catalog, 'scalargame', 'head-to-head')[0]?.id ?? '' } })
    expect(planProblems(catalog, plan)).toEqual([
      'Music for head-to-head: choose the calm rotation or a bed of the right game and length.',
      'Music for missing-slot: choose the calm rotation or a bed of the right game and length.',
    ])
  })

  it('needs at least one episode, an existing project and no pilots for Originals', () => {
    expect(planProblems(catalog, scalar({ scope: scalar().scope.map((r) => ({ ...r, count: 0, mix: [0, 0, 0] })) }))).toEqual(['Choose at least one episode.'])
    expect(planProblems(catalog, { ...scalar(), project: 'nope' })).toEqual(['Unknown project “nope”.'])
    const originals = { ...defaultPlan(catalog, 'originals', '2026-11-originals-01'), pilots: true, subjects: 'Arrival' }
    expect(planProblems(catalog, originals)).toEqual(['Originals has no pilot step.'])
  })
})

describe('Scalargame prompt', () => {
  it('fills the brief from the plan and ends with the safety lines', () => {
    const music = { ...scalar().music, 'head-to-head': 'continuum-20-holizna-clouds' }
    const plan = scalar({
      goal: 'Test shorter\nhooks',
      scope: scalar().scope.map((r) => (r.format === 'progressive-clues' ? { ...r, count: 4, mix: [2, 1, 1] } : r.format === 'head-to-head' ? r : { ...r, count: 0, mix: [0, 0, 0] })),
      pilots: true,
      music,
      experimentId: 'hooks-2026-11',
      prefer: 'islands',
      avoid: 'capitals',
      notes: '- shorter hook text',
    })
    expect(planProblems(catalog, plan)).toEqual([])
    const brief = buildPlanBrief(catalog, plan, { openFeedback: [feedback], lastRetro: null })
    const section = (name: string) => (brief.split(`## ${name}\n`)[1]?.split('\n\n')[0] ?? '').trimEnd()
    expect(section('Goals')).toBe('- Test shorter hooks')
    expect(section('Mix')).toBe(
      [
        '- Episodes: 7 main, plus 1 spare per format',
        '- scalar / progressive-clues: 4 (approachable 2, moderate 1, challenging 1)',
        '- continuum / head-to-head: 3 (approachable 1, moderate 1, challenging 1)',
        '- Pilots first: yes, one per game, then Checkpoint 2',
        '- Styles: scalar → scalar-notebook-1; continuum → continuum-poster-1',
        '- Music: progressive-clues → calm rotation; head-to-head → continuum-20-holizna-clouds (“Clouds”, HoliznaCC0, CC0-1.0)',
        '- Prefer: islands',
        '- Avoid: capitals',
      ].join('\n'),
    )
    expect(section('Experiments')).toBe('- Experiment ID: hooks-2026-11\n- shorter hook text')
    expect(section('What worked')).toContain('scalar-clues-001 rev 1')
    const prompt = buildPlanPrompt(catalog, plan, brief)
    expect(prompt.startsWith('/video-batch brief 2026-11-b02\n\n# Brief: 2026-11-b02\n')).toBe(true)
    expect(prompt).toContain('\n\nFeedback file: library/_inbox/feedback-2026-11-b02.json\n\n')
    expect(prompt.endsWith(SAFETY)).toBe(true)
  })
})

describe('Originals prompt', () => {
  it('hands off to /originals with models from the catalog, budget, platforms and the safety lines', () => {
    const plan = {
      ...defaultPlan(catalog, 'originals', '2026-11-o01'),
      goal: 'First recap',
      subjects: 'Arrival (2016)\n- Heat (1995)\n',
      avoid: 'spoilers in the hook',
    }
    expect(planProblems(catalog, plan)).toEqual([])
    const brief = buildPlanBrief(catalog, plan, null)
    expect(brief).toContain('# Brief: 2026-11-o01 (Originals)')
    expect(brief).toContain('## Mix\n- Episodes: 1\n- movie-recap (Story · recap): 1\n')
    expect(brief).toContain('## Subjects\n- Arrival (2016)\n- Heat (1995)\n')
    expect(brief).toMatch(/## Models \(catalog\)\n- movie-recap: script gemini-2\.5-flash \(fallback llama-3\.3-70b-versatile\), narration gemini-2\.5-flash-preview-tts/)
    expect(brief).toContain('X and Bluesky get no caption')
    expect(brief).toContain('- Mix: no target set yet')
    expect(brief).toContain('## Budget\n- Monthly budget: $0; every paid run needs my OK for that run, with a cost estimate.')
    expect(brief).toContain('## Checks\n- Rights, Script sanity, Visual QA, AI disclosure, Batch contract')
    expect(brief).toContain('## Avoid\n- spoilers in the hook')
    const prompt = buildPlanPrompt(catalog, plan, brief)
    expect(prompt.startsWith('/originals brief 2026-11-o01\n')).toBe(true)
    expect(prompt).toContain('finalize only on my approval')
    expect(prompt).toContain('cost estimate')
    expect(prompt.endsWith(SAFETY)).toBe(true)
    expect(prompt).not.toContain('/video-batch')
  })

  it('animated shorts need a verified video model from the catalog', () => {
    const base = defaultPlan(catalog, 'originals', '2026-11-o02')
    const scope = base.scope.map((r) => (r.format === 'animated-short' ? { ...r, count: 2 } : { ...r, count: 0 }))
    const plan = { ...base, scope, subjects: 'Galactic Garage: alien mechanics fix spaceships' }
    expect(plansGeneratedVideo(catalog, plan)).toBe(true)
    expect(plan.videoModel).toBe('veo-3.1-fast')
    expect(planProblems(catalog, plan)).toEqual([])
    expect(buildPlanBrief(catalog, plan, null)).toMatch(/- animated-short: story and shots .*video Veo 3\.1 Fast \(veo-3\.1-fast, \$0\.1\/s, 8 s a shot, native audio\)/)
    expect(planProblems(catalog, { ...plan, videoModel: 'sora-2-pro' })).toContain('Choose a video model for the animated shorts.')
    expect(storyVideoModels(catalog).map((m) => m.id)).not.toContain('sora-2-pro')
  })
})

describe('presets', () => {
  it('save, list newest first, replace by name, delete; never store the batch id', () => {
    const storage = memoryStorage()
    expect(readPresets(storage)).toEqual([])
    expect(savePreset('Weekly', scalar({ goal: 'a' }), storage)).toBe(true)
    expect(savePreset('Hooks', scalar({ goal: 'b' }), storage)).toBe(true)
    expect(savePreset('Weekly', scalar({ goal: 'c' }), storage)).toBe(true)
    expect(readPresets(storage).map((p) => [p.name, p.plan.goal])).toEqual([['Weekly', 'c'], ['Hooks', 'b']])
    expect(storage.getItem(PRESETS_KEY)).not.toContain('2026-11-b02')
    expect(deletePreset('Hooks', storage)).toBe(true)
    expect(readPresets(storage).map((p) => p.name)).toEqual(['Weekly'])
    expect(savePreset('   ', scalar(), storage)).toBe(false)
  })

  it('keeps at most MAX_PRESETS', () => {
    const storage = memoryStorage()
    for (let i = 0; i < MAX_PRESETS + 3; i++) savePreset(`p${i}`, scalar(), storage)
    expect(readPresets(storage)).toHaveLength(MAX_PRESETS)
    expect(readPresets(storage)[0]?.name).toBe(`p${MAX_PRESETS + 2}`)
  })

  it('survives blocked storage and garbage', () => {
    expect(readPresets(blocked)).toEqual([])
    expect(savePreset('x', scalar(), blocked)).toBe(false)
    expect(readPresets(null)).toEqual([])
    expect(readPresets(memoryStorage({ [PRESETS_KEY]: '{not json' }))).toEqual([])
    expect(readPresets(memoryStorage({ [PRESETS_KEY]: JSON.stringify([1, { name: 'x' }, { name: 'ok', plan: { project: 'scalargame', scope: [{ format: 'a', count: -1 }] } }]) }))).toEqual([
      expect.objectContaining({ name: 'ok', plan: expect.objectContaining({ scope: [] }) }),
    ])
  })

  it('applies a preset with only what the catalog still offers', () => {
    const storage = memoryStorage()
    savePreset(
      'Old',
      scalar({
        scope: [
          { format: 'progressive-clues', count: 2, mix: [1, 1, 0] },
          { format: 'retired-format', count: 5, mix: [5, 0, 0] },
        ],
        styles: { scalar: 'scalar-notebook-0', continuum: 'continuum-poster-1' },
        music: { 'progressive-clues': 'gone-bed', 'head-to-head': 'continuum-20-holizna-clouds' },
      }),
      storage,
    )
    const preset = readPresets(storage)[0]
    expect(preset).toBeDefined()
    if (!preset) return
    const plan = applyPreset(catalog, preset, '2026-12-b03')
    expect(plan?.batchId).toBe('2026-12-b03')
    expect(plan?.scope.filter((r) => r.count > 0)).toEqual([{ format: 'progressive-clues', count: 2, mix: [1, 1, 0] }])
    expect(plan?.scope.some((r) => r.format === 'retired-format')).toBe(false)
    expect(plan?.styles.scalar).toBe('scalar-notebook-1')
    expect(plan?.music['progressive-clues']).toBe(CALM)
    expect(plan?.music['head-to-head']).toBe('continuum-20-holizna-clouds')
    expect(plan && planProblems(catalog, plan)).toEqual([])
    expect(applyPreset(catalog, { ...preset, plan: { ...preset.plan, project: 'gone' } }, '2026-12-b03')).toBeNull()
  })
})
