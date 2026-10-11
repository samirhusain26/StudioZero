import { describe, expect, it } from 'vitest'
import { libraryFixture } from '../test/libraryFixture'
import { approvableShown, batchChips, DEFAULT_LIST, filterCounts, listEpisodes, position, readListState, writeListState } from './libraryList'

const ids = (list: { episodeId: string }[]) => list.map((e) => e.episodeId)

describe('library list', () => {
  it('defaults to To review across all batches; withdrawn counts as to review', () => {
    const data = libraryFixture()
    expect(ids(listEpisodes(data, DEFAULT_LIST))).toEqual(['scalar-clues-001', 'scalar-clues-003', 'scalar-legacy-001'])
    expect(ids(listEpisodes(data, { batchId: '2026-10-b01', filter: 'approved' }))).toEqual(['scalar-clues-002'])
    expect(listEpisodes(data, { batchId: '', filter: 'all' })).toHaveLength(4)
    expect(filterCounts(data, '2026-10-b01')).toEqual({ review: 2, approved: 1, all: 3 })
  })

  it('keeps the episode being reviewed in its list after it is approved', () => {
    const data = libraryFixture()
    const list = listEpisodes(data, DEFAULT_LIST, { episodeId: 'scalar-clues-002', revision: 1 })
    expect(ids(list)).toEqual(['scalar-clues-001', 'scalar-clues-002', 'scalar-clues-003', 'scalar-legacy-001'])
    expect(position(list, 'scalar-clues-002', 1)).toMatchObject({ index: 1, total: 4, previous: { episodeId: 'scalar-clues-001' }, next: { episodeId: 'scalar-clues-003' } })
    expect(position(list, 'scalar-clues-001', 1)).toMatchObject({ previous: null })
    expect(position(list, 'nope', 1)).toMatchObject({ index: -1, previous: null, next: null })
  })

  it('lists batch chips newest first, legacy shortened', () => {
    expect(batchChips(libraryFixture())).toEqual([
      { batchId: '2026-10-b01', label: '2026-10-b01', count: 3 },
      { batchId: 'legacy-2026-10-05', label: 'legacy', count: 1 },
    ])
  })

  it('approves only shown, approvable episodes without problems', () => {
    const data = libraryFixture()
    const shown = listEpisodes(data, { batchId: '', filter: 'all' })
    const flagged = shown.map((e, i) => (i === 0 ? { ...e, problems: [{ code: 'media', path: 'video', message: 'Bad' }] } : e))
    expect(ids(approvableShown(flagged))).toEqual(['scalar-clues-003', 'scalar-legacy-001'])
  })

  it('remembers the list for this tab, ignoring junk', () => {
    const store = new Map<string, string>()
    const storage = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) } as unknown as Storage
    expect(readListState(storage)).toEqual(DEFAULT_LIST)
    writeListState({ batchId: '2026-10-b01', filter: 'approved' }, storage)
    expect(readListState(storage)).toEqual({ batchId: '2026-10-b01', filter: 'approved' })
    store.set('scalar-library-list', '{"filter":"evil","batchId":3}')
    expect(readListState(storage)).toEqual(DEFAULT_LIST)
  })
})
