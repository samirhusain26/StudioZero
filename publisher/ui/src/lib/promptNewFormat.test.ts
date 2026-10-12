import { describe, expect, it } from 'vitest'
import { realCatalog } from '../test/catalog'
import { SAFETY_LINES } from './promptSafety'
import { buildNewFormatPrompt, defaultNewPlan, newPlanProblems, readDraft, slugOf, writeDraft, type NewFormatPlan } from './promptNewFormat'

const NOW = new Date('2026-11-03T10:00:00Z')

function memory(): Storage {
  const data = new Map<string, string>()
  return {
    get length() { return data.size },
    clear: () => data.clear(),
    getItem: (k: string) => data.get(k) ?? null,
    key: (i: number) => [...data.keys()][i] ?? null,
    removeItem: (k: string) => { data.delete(k) },
    setItem: (k: string, v: string) => { data.set(k, v) },
  }
}

const motionFormat = (over: Partial<NewFormatPlan> = {}): NewFormatPlan => ({
  ...defaultNewPlan(realCatalog()),
  kind: 'format',
  project: 'scalargame',
  engine: 'motion',
  game: 'scalar',
  baseFormat: 'progressive-clues',
  name: 'Border Run',
  topic: 'Trace a country’s border from its neighbours.',
  vocabulary: ['map zooms', 'counters'],
  ...over,
})

describe('prompt builder mode 2', () => {
  it('slugs names', () => {
    expect(slugOf('  Border Run! (v2) ')).toBe('border-run-v2')
    expect(slugOf('Café Crème')).toBe('cafe-creme')
  })

  it('a motion format: build, browser limits, pilot bundle for the Player, ask before pushing, safety lines last', () => {
    const catalog = realCatalog()
    expect(newPlanProblems(catalog, motionFormat())).toEqual([])
    const prompt = buildNewFormatPrompt(catalog, motionFormat(), NOW)
    expect(prompt).toMatch(/^New format “Border Run” \(id border-run\) for project scalargame, on the /)
    expect(prompt).toContain('- Start from: ')
    expect(prompt).toContain('- Structure, in order: hook → body → thinking timer → reveal → call to action')
    expect(prompt).toContain('engines/motion/src/projects/scalargame/')
    expect(prompt).toContain('no z-index')
    expect(prompt).toContain('web-jobs.mjs --batch=2026-11-pilot-border-run')
    expect(prompt).toContain('Studio › Export')
    expect(prompt).toContain('ask me before pushing')
    expect(prompt.endsWith(SAFETY_LINES.join('\n'))).toBe(true)
  })

  it('a story format runs a $0 pilot first and a paid one only after a confirmed estimate', () => {
    const catalog = realCatalog()
    const plan = motionFormat({ project: 'originals', engine: 'story', route: 'series', game: '', baseFormat: 'animated-short', name: 'Kitchen Wars' })
    expect(newPlanProblems(catalog, plan)).toEqual([])
    const prompt = buildNewFormatPrompt(catalog, plan, NOW)
    expect(prompt).toContain('(series route)')
    expect(prompt).toContain('$0 dry run')
    expect(prompt).toContain('only after I confirm that estimate')
    expect(prompt).toContain('Studio › Story renders')
    expect(prompt).not.toContain('web-jobs.mjs')
  })

  it('a new project leaves budget and mix to the owner and does not touch the contract', () => {
    const catalog = realCatalog()
    const plan = motionFormat({ kind: 'project', project: '', projectName: 'Word Lab', game: '', baseFormat: '', name: 'Anagram Sprint' })
    expect(newPlanProblems(catalog, plan)).toEqual([])
    const prompt = buildNewFormatPrompt(catalog, plan, NOW)
    expect(prompt).toContain('projects/word-lab/project.json')
    expect(prompt).toContain('both are my decisions')
    expect(prompt).toContain('do not change the contract')
  })

  it('refuses what the catalog cannot back', () => {
    const catalog = realCatalog()
    expect(newPlanProblems(catalog, motionFormat({ name: 'Progressive Clues' }))).toContain('“progressive-clues” already exists in the catalog; pick another name.')
    expect(newPlanProblems(catalog, motionFormat({ kind: 'style', engine: 'story', route: 'series', game: '' }))).toEqual(
      expect.arrayContaining(['Choose the game the style is for.', expect.stringContaining('a style needs the motion engine')]),
    )
    expect(newPlanProblems(catalog, motionFormat({ engine: 'story', route: '' }))).toContain('Choose a Story route.')
    expect(newPlanProblems(catalog, motionFormat({ baseFormat: 'movie-recap' }))).toContain('The format to start from must be one of this project’s formats on the same engine.')
    expect(newPlanProblems(catalog, motionFormat({ beats: [], lengthSeconds: 200, topic: '' }))).toEqual(
      expect.arrayContaining(['Keep at least one beat in the structure.', 'Length: 8 to 90 seconds.', 'Describe the topic.']),
    )
    expect(newPlanProblems(catalog, motionFormat({ game: 'nope' }))).toContain('That game is not in this project.')
  })

  it('keeps a draft in this browser and repairs it against the catalog', () => {
    const catalog = realCatalog()
    const storage = memory()
    expect(writeDraft({ ...motionFormat(), engine: 'gone', vocabulary: ['counters', 'lasers'], beats: ['reveal', 'hook'] }, storage)).toBe(true)
    const draft = readDraft(catalog, storage)
    expect(draft.name).toBe('Border Run')
    expect(draft.engine).toBe(defaultNewPlan(catalog).engine)
    expect(draft.vocabulary).toEqual(['counters'])
    expect(draft.beats).toEqual(['hook', 'reveal'])
    storage.setItem('studio-new-format-draft', '{broken')
    expect(readDraft(catalog, storage)).toEqual(defaultNewPlan(catalog))
    expect(readDraft(catalog, null)).toEqual(defaultNewPlan(catalog))
  })
})
