import { describe, expect, it } from 'vitest'
import type { JobBundle, JobInput } from './bundle'
import { episodeRows, isPhone, readyToPackage, remaining } from './exportState'
import { memoryStore, type StoredExport } from './store'

const job = (id: string, hash = 'a'.repeat(64)): JobInput =>
  ({ episodeId: id, propsHash: hash, props: { q: { game: 'scalar', format: 'progressive-clues' } } }) as unknown as JobInput
const bundle = { batchId: '2026-10-webtest', jobs: [job('a'), job('b'), job('c', 'c'.repeat(64)), job('d')] } as unknown as JobBundle
const done = (id: string, over: Partial<StoredExport> = {}): StoredExport =>
  ({ batchId: '2026-10-webtest', episodeId: id, propsHash: 'a'.repeat(64), errors: [], ...over }) as StoredExport

describe('export state', () => {
  it('derives each episode status', () => {
    const rows = episodeRows(bundle, [done('a'), done('b', { errors: ['true peak -0.5 dBTP above −1'] }), done('c')], 'd')
    expect(rows.map((r) => [r.episodeId, r.status])).toEqual([['a', 'passed'], ['b', 'failed'], ['c', 'stale'], ['d', 'interrupted']])
    expect(readyToPackage(rows)).toBe(false)
    expect(remaining(rows)).toEqual(['b', 'c', 'd'])
    const all = episodeRows(bundle, ['a', 'b', 'd'].map((id) => done(id)).concat(done('c', { propsHash: 'c'.repeat(64) })), null)
    expect(readyToPackage(all)).toBe(true)
    expect(readyToPackage([])).toBe(false)
  })

  it('tells phones from laptops', () => {
    expect(isPhone({ userAgentData: { mobile: true } }, false)).toBe(true)
    expect(isPhone({}, true)).toBe(true)
    expect(isPhone(undefined, false)).toBe(false)
  })

  it('keeps exports per batch in the memory fallback', async () => {
    const store = memoryStore()
    await store.putBundle({ batchId: '2026-10-webtest', text: '{}', savedAt: 'x' })
    await store.putExport(done('a'))
    await store.putExport({ ...done('a'), batchId: 'other' })
    await store.markRunning('2026-10-webtest', 'b')
    expect((await store.getExports('2026-10-webtest')).map((e) => e.episodeId)).toEqual(['a'])
    expect(await store.running('2026-10-webtest')).toBe('b')
    await store.clear('2026-10-webtest')
    expect(await store.getBundle()).toBeNull()
    expect(await store.getExports('2026-10-webtest')).toEqual([])
    expect(await store.getExports('other')).toHaveLength(1)
    expect(store.durable).toBe(false)
  })
})
