/**
 * Hand-posted projects on Studio › Overview (studio.json manualProjects): the ISO week a weekly prompt is for, the
 * prompt text and the countdown to the project's goal. Pure; dates are the device's local calendar days.
 */

export interface IsoWeek {
  /** "2026-W42" */
  id: string
  /** YYYY-MM-DD */
  monday: string
  sunday: string
}

function dayKey(date: Date): string {
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, '0')}-${String(date.getUTCDate()).padStart(2, '0')}`
}

/** The local calendar day of `now` as a UTC-midnight date, so day arithmetic ignores time zones and DST. */
function localDay(now: Date): Date {
  return new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()))
}

/** The ISO week (Monday to Sunday) holding `now`'s local day, `offset` weeks later (−1 = last week). */
export function isoWeek(now: Date, offset = 0): IsoWeek {
  const day = localDay(now)
  day.setUTCDate(day.getUTCDate() + offset * 7)
  const weekday = day.getUTCDay() || 7
  const monday = new Date(day)
  monday.setUTCDate(day.getUTCDate() - weekday + 1)
  const sunday = new Date(monday)
  sunday.setUTCDate(monday.getUTCDate() + 6)
  // The ISO year is the year of the week's Thursday; week 1 holds that year's first Thursday.
  const thursday = new Date(monday)
  thursday.setUTCDate(monday.getUTCDate() + 3)
  const year = thursday.getUTCFullYear()
  const week = Math.floor((thursday.getTime() - Date.UTC(year, 0, 1)) / 86_400_000 / 7) + 1
  return { id: `${year}-W${String(week).padStart(2, '0')}`, monday: dayKey(monday), sunday: dayKey(sunday) }
}

/** Fills {week}, {monday} and {sunday}; the exporter refuses any other placeholder. */
export function fillPrompt(template: string, week: IsoWeek): string {
  return template.replaceAll('{week}', week.id).replaceAll('{monday}', week.monday).replaceAll('{sunday}', week.sunday)
}

/** Whole days from `now`'s local day to a YYYY-MM-DD date (0 on the day, negative after it). */
export function daysUntil(now: Date, date: string): number {
  return Math.round((new Date(`${date}T00:00:00Z`).getTime() - localDay(now).getTime()) / 86_400_000)
}
