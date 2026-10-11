/**
 * Time display helpers. All zone names and abbreviations come from Intl; nothing
 * about DST is hard-coded here.
 */

interface ZonedParts {
  weekday: string
  day: string
  month: string
  hour: string
  minute: string
  zone: string
  year: string
}

const partsCache = new Map<string, Intl.DateTimeFormat>()

function formatter(zone: string): Intl.DateTimeFormat {
  let f = partsCache.get(zone)
  if (!f) {
    // en-US yields zone abbreviations such as EDT/EST where Intl knows them,
    // otherwise an offset such as GMT+1.
    f = new Intl.DateTimeFormat('en-US', {
      timeZone: zone,
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
      timeZoneName: 'short',
    })
    partsCache.set(zone, f)
  }
  return f
}

function zonedParts(date: Date, zone: string): ZonedParts {
  const out: Record<string, string> = {}
  for (const part of formatter(zone).formatToParts(date)) out[part.type] = part.value
  return {
    weekday: out.weekday ?? '',
    day: out.day ?? '',
    month: out.month ?? '',
    hour: out.hour === '24' ? '00' : (out.hour ?? ''),
    minute: out.minute ?? '',
    zone: out.timeZoneName ?? zone,
    year: out.year ?? '',
  }
}

export function isValidTimeZone(zone: string): boolean {
  if (!zone.trim()) return false
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: zone })
    return true
  } catch {
    return false
  }
}

function parse(iso: string): Date | null {
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? null : date
}

/** Zone abbreviation (from Intl) at a given instant, e.g. "EDT" or "EST". */
export function zoneAbbreviation(iso: string, zone: string): string {
  const date = parse(iso)
  return date ? zonedParts(date, zone).zone : zone
}

/** "Mon 12 Oct, 09:00 EDT" */
export function formatLocal(iso: string, zone: string): string {
  const date = parse(iso)
  if (!date) return iso
  const p = zonedParts(date, zone)
  return `${p.weekday} ${p.day} ${p.month}, ${p.hour}:${p.minute} ${p.zone}`
}

/**
 * "Mon 12 Oct, 09:00 EDT · 13:00 UTC". When the UTC calendar day differs from the
 * local one, the UTC part carries its own date: "… · Tue 13 Oct, 01:00 UTC".
 */
export function formatLocalAndUtc(iso: string, zone: string): string {
  const date = parse(iso)
  if (!date) return iso
  const local = zonedParts(date, zone)
  const utc = zonedParts(date, 'UTC')
  const localText = `${local.weekday} ${local.day} ${local.month}, ${local.hour}:${local.minute} ${local.zone}`
  const sameDay = local.day === utc.day && local.month === utc.month && local.year === utc.year
  const utcText = sameDay
    ? `${utc.hour}:${utc.minute} UTC`
    : `${utc.weekday} ${utc.day} ${utc.month}, ${utc.hour}:${utc.minute} UTC`
  return `${localText} · ${utcText}`
}

/** Local calendar date key (YYYY-MM-DD) in a zone, for grouping by day. */
export function localDateKey(iso: string, zone: string): string {
  const date = parse(iso)
  if (!date) return iso.slice(0, 10)
  const f = new Intl.DateTimeFormat('en-CA', { timeZone: zone, year: 'numeric', month: '2-digit', day: '2-digit' })
  return f.format(date)
}

/** "Monday 12 October 2026" for a YYYY-MM-DD key (calendar date, zone-free). */
export function formatDayHeading(dateKey: string): string {
  const date = new Date(`${dateKey}T12:00:00Z`)
  if (Number.isNaN(date.getTime())) return dateKey
  return new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(date)
}

/** "4 min ago" style relative age from seconds. */
export function formatAge(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return 'unknown'
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))} s ago`
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`
  return `${Math.round(seconds / 86400)} d ago`
}

/** The device zone, used only as a display fallback. */
export function deviceTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

/** "14:03:27 EDT" for the "Updated" line. */
export function formatClock(date: Date, zone: string): string {
  try {
    const parts: Record<string, string> = {}
    const f = new Intl.DateTimeFormat('en-US', {
      timeZone: zone,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
      timeZoneName: 'short',
    })
    for (const part of f.formatToParts(date)) parts[part.type] = part.value
    return `${parts.hour === '24' ? '00' : parts.hour}:${parts.minute}:${parts.second} ${parts.timeZoneName ?? zone}`
  } catch {
    return date.toISOString().slice(11, 19) + ' UTC'
  }
}

/** "09:00 EDT · 13:00 UTC" (time of day only; the day is the group heading). */
export function formatTimeLocalAndUtc(iso: string, zone: string): string {
  const date = parse(iso)
  if (!date) return iso
  const local = zonedParts(date, zone)
  const utc = zonedParts(date, 'UTC')
  const sameDay = local.day === utc.day && local.month === utc.month && local.year === utc.year
  const utcText = sameDay ? `${utc.hour}:${utc.minute} UTC` : `${utc.weekday} ${utc.day} ${utc.month}, ${utc.hour}:${utc.minute} UTC`
  return `${local.hour}:${local.minute} ${local.zone} · ${utcText}`
}
