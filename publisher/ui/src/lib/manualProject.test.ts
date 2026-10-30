import { describe, expect, it } from 'vitest'
import { daysUntil, fillPrompt, isoWeek } from './manualProject'

const at = (y: number, m: number, d: number, h = 12) => new Date(y, m - 1, d, h)

describe('manual projects', () => {
  it('isoWeek: Monday to Sunday, the ISO year at year ends, and last week', () => {
    expect(isoWeek(at(2026, 10, 18))).toEqual({ id: '2026-W42', monday: '2026-10-12', sunday: '2026-10-18' })
    expect(isoWeek(at(2026, 10, 12, 0))).toEqual({ id: '2026-W42', monday: '2026-10-12', sunday: '2026-10-18' })
    expect(isoWeek(at(2026, 10, 19), -1).id).toBe('2026-W42')
    expect(isoWeek(at(2027, 1, 3)).id).toBe('2026-W53')
    expect(isoWeek(at(2025, 12, 29)).id).toBe('2026-W01')
    expect(isoWeek(at(2028, 1, 2)).id).toBe('2027-W52')
  })

  it('fillPrompt replaces every placeholder', () => {
    const week = isoWeek(at(2026, 10, 18))
    expect(fillPrompt('/marathon-week {week}\n{monday}–{sunday}, {week}', week)).toBe('/marathon-week 2026-W42\n2026-10-12–2026-10-18, 2026-W42')
  })

  it('daysUntil counts local calendar days', () => {
    expect(daysUntil(at(2026, 10, 12, 23), '2028-11-05')).toBe(755)
    expect(daysUntil(at(2028, 11, 5, 1), '2028-11-05')).toBe(0)
    expect(daysUntil(at(2028, 11, 6), '2028-11-05')).toBe(-1)
  })
})
