import { describe, expect, it } from 'vitest'
import { formatLocal, formatLocalAndUtc, isValidTimeZone, localDateKey, zoneAbbreviation } from './time'

const NY = 'America/New_York'

describe('formatLocalAndUtc', () => {
  it('formats the documented example', () => {
    expect(formatLocalAndUtc('2026-10-12T13:00:00Z', NY)).toBe('Mon 12 Oct, 09:00 EDT · 13:00 UTC')
  })

  it('accepts +00:00 offsets', () => {
    expect(formatLocalAndUtc('2026-10-12T13:00:00+00:00', NY)).toBe('Mon 12 Oct, 09:00 EDT · 13:00 UTC')
  })

  it('switches EDT to EST across the 2026-11-01 fall-back', () => {
    // 01:30 happens twice on 1 November 2026: first EDT (05:30Z), then EST (06:30Z).
    expect(formatLocalAndUtc('2026-11-01T05:30:00Z', NY)).toBe('Sun 1 Nov, 01:30 EDT · 05:30 UTC')
    expect(formatLocalAndUtc('2026-11-01T06:30:00Z', NY)).toBe('Sun 1 Nov, 01:30 EST · 06:30 UTC')
    expect(formatLocalAndUtc('2026-11-02T14:00:00Z', NY)).toBe('Mon 2 Nov, 09:00 EST · 14:00 UTC')
    expect(zoneAbbreviation('2026-10-31T13:00:00Z', NY)).toBe('EDT')
    expect(zoneAbbreviation('2026-11-01T13:00:00Z', NY)).toBe('EST')
  })

  it('switches EST to EDT across the 2027-03-14 spring-forward', () => {
    expect(formatLocalAndUtc('2027-03-14T06:30:00Z', NY)).toBe('Sun 14 Mar, 01:30 EST · 06:30 UTC')
    // 02:00–02:59 local does not exist; 07:30Z is 03:30 EDT.
    expect(formatLocalAndUtc('2027-03-14T07:30:00Z', NY)).toBe('Sun 14 Mar, 03:30 EDT · 07:30 UTC')
    expect(formatLocalAndUtc('2027-03-15T13:00:00Z', NY)).toBe('Mon 15 Mar, 09:00 EDT · 13:00 UTC')
    expect(zoneAbbreviation('2027-03-13T14:00:00Z', NY)).toBe('EST')
  })

  it('adds the UTC date when it differs from the local date', () => {
    expect(formatLocalAndUtc('2026-10-12T02:00:00Z', NY)).toBe('Sun 11 Oct, 22:00 EDT · Mon 12 Oct, 02:00 UTC')
  })

  it('takes abbreviations from Intl for other zones', () => {
    const intl = new Intl.DateTimeFormat('en-US', { timeZone: 'Europe/London', timeZoneName: 'short' })
      .formatToParts(new Date('2026-07-01T12:00:00Z'))
      .find((p) => p.type === 'timeZoneName')?.value
    expect(formatLocal('2026-07-01T12:00:00Z', 'Europe/London')).toBe(`Wed 1 Jul, 13:00 ${intl}`)
  })

  it('returns the input unchanged when unparsable', () => {
    expect(formatLocalAndUtc('not a date', NY)).toBe('not a date')
  })
})

describe('zone helpers', () => {
  it('validates IANA names', () => {
    expect(isValidTimeZone('America/New_York')).toBe(true)
    expect(isValidTimeZone('Mars/Olympus')).toBe(false)
    expect(isValidTimeZone('')).toBe(false)
  })

  it('groups by local calendar date', () => {
    expect(localDateKey('2026-10-12T02:00:00Z', NY)).toBe('2026-10-11')
    expect(localDateKey('2026-10-12T13:00:00Z', NY)).toBe('2026-10-12')
  })
})
