import { describe, expect, it } from 'vitest'
import { emptyMake, MAKE_KEY_PREFIX, makeComplete, pruneMake, readMake, writeMake } from './makeChecklist'

function memoryStorage(): Storage {
  const data = new Map<string, string>()
  return {
    get length() {
      return data.size
    },
    clear: () => data.clear(),
    getItem: (k) => data.get(k) ?? null,
    key: (i) => [...data.keys()][i] ?? null,
    removeItem: (k) => void data.delete(k),
    setItem: (k, v) => void data.set(k, String(v)),
  }
}

describe('Make checklist (browser-local, per batch id)', () => {
  it('round-trips progress and ignores unknown checkpoints', () => {
    const s = memoryStorage()
    expect(readMake('2026-10-b02', s)).toEqual(emptyMake('2026-10-b02'))
    writeMake({ batchId: '2026-10-b02', started: true, checks: ['c0', 'c1'] }, s)
    expect(readMake('2026-10-b02', s)).toEqual({ batchId: '2026-10-b02', started: true, checks: ['c0', 'c1'] })
    s.setItem(`${MAKE_KEY_PREFIX}2026-10-b03`, JSON.stringify({ checks: ['c0', 'nope', 'c0'] }))
    expect(readMake('2026-10-b03', s)).toEqual({ batchId: '2026-10-b03', started: true, checks: ['c0'] })
    s.setItem(`${MAKE_KEY_PREFIX}2026-10-b04`, '{not json')
    expect(readMake('2026-10-b04', s)).toEqual(emptyMake('2026-10-b04'))
  })

  it('carries the same bNN over a month rollover', () => {
    const s = memoryStorage()
    writeMake({ batchId: '2026-10-b02', started: true, checks: ['c3'] }, s)
    expect(readMake('2026-11-b02', s)).toEqual({ batchId: '2026-11-b02', started: true, checks: ['c3'] })
    expect(readMake('2026-11-b03', s)).toEqual(emptyMake('2026-11-b03'))
  })

  it('prunes checklists for batches that have arrived', () => {
    const s = memoryStorage()
    writeMake({ batchId: '2026-10-b01', started: true, checks: ['finalize'] }, s)
    writeMake({ batchId: '2026-10-b02', started: true, checks: [] }, s)
    s.setItem(`${MAKE_KEY_PREFIX}garbage`, '{}')
    s.setItem('unrelated', 'x')
    pruneMake('2026-10-b02', s)
    expect([...Array(s.length).keys()].map((i) => s.key(i)).sort()).toEqual([`${MAKE_KEY_PREFIX}2026-10-b02`, 'unrelated'])
  })

  it('is complete once Finalize is ticked, and survives blocked storage', () => {
    expect(makeComplete({ batchId: 'x', started: true, checks: ['c0', 'c1', 'c3'] })).toBe(false)
    expect(makeComplete({ batchId: 'x', started: true, checks: ['finalize'] })).toBe(true)
    expect(makeComplete(null)).toBe(false)
    const blocked = memoryStorage()
    blocked.setItem = () => {
      throw new Error('QuotaExceeded')
    }
    expect(() => writeMake(emptyMake('2026-10-b02'), blocked)).not.toThrow()
    expect(readMake('2026-10-b02', null)).toEqual(emptyMake('2026-10-b02'))
  })
})
