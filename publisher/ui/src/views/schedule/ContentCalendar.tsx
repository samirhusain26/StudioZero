import { useId, useState } from 'react'
import type { LibraryEpisode, QueueJob, ScheduleResponse } from '../../api/types'
import { StatusBadge } from '../../components/StatusBadge'
import { platformName } from '../../lib/format'
import { ledgerStatus, type Tone } from '../../lib/labels'
import { calendarMonths, computeRunway, type CalendarDay } from '../../lib/runway'
import { formatDayHeading, formatTimeLocalAndUtc } from '../../lib/time'

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

/** "Thu 29 Oct" for a YYYY-MM-DD key. */
export function shortDay(dateKey: string): string {
  const date = new Date(`${dateKey}T12:00:00Z`)
  if (Number.isNaN(date.getTime())) return dateKey
  return new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', weekday: 'short', day: 'numeric', month: 'short' }).format(date)
}

/** "29 Oct": the weekday is left out to keep the table phone-width. */
function dayMonth(dateKey: string): string {
  return new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', day: 'numeric', month: 'short' }).format(new Date(`${dateKey}T12:00:00Z`))
}

function monthName(month: string): string {
  return new Intl.DateTimeFormat('en-GB', { timeZone: 'UTC', month: 'long', year: 'numeric' }).format(new Date(`${month}-15T12:00:00Z`))
}

/** Dot colour: published, failed or missed, in flight, otherwise scheduled. */
function jobTone(job: QueueJob): Tone {
  const tone = ledgerStatus(job.status).tone
  return tone === 'neutral' ? 'info' : tone
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? '' : 's'}`
}

function dayLabel(day: CalendarDay, projected: boolean): string {
  const posted = day.posts.filter((j) => j.status === 'confirmed').length
  const parts = [formatDayHeading(day.dateKey)]
  if (day.posts.length) parts.push(plural(day.posts.length, 'post') + (posted ? `, ${posted} published` : ''))
  else parts.push(projected ? 'nothing scheduled; approved videos could fill it' : 'nothing scheduled')
  return parts.join(': ')
}

/**
 * Content calendar: how far the approved queue reaches, per platform, and how much further the approved but
 * unscheduled videos would take it at one a day. Tap a day to list its posts.
 */
export function ContentCalendar({
  schedule,
  episodes,
  now = new Date(),
}: {
  schedule: ScheduleResponse
  episodes: readonly LibraryEpisode[] | null
  now?: Date
}) {
  const id = useId()
  const zone = schedule.displayTimezone
  const runway = computeRunway(schedule, episodes, now)
  const [selected, setSelected] = useState<string | null>(null)
  const reach = runway.platforms.map((p) => p.couldReach).filter((d): d is string => Boolean(d)).sort()
  const projectedEnd = reach.at(-1) ?? null
  const scheduledEnd = runway.lastDay && runway.lastDay >= runway.today ? runway.lastDay : null
  const to = [scheduledEnd, projectedEnd].filter((d): d is string => Boolean(d)).sort().at(-1) ?? runway.today
  const months = calendarMonths(schedule.jobs, zone, runway.today, to)
  const selectedDay = selected ? months.flatMap((m) => m.weeks.flat()).find((d) => d.dateKey === selected && d.inMonth) : undefined
  const gapIsToday = runway.firstGap === runway.today

  return (
    <section className="card stack" aria-labelledby={`${id}-h`} data-testid="content-calendar">
      <h2 id={`${id}-h`}>Content calendar</h2>
      {runway.platforms.length === 0 ? (
        <p className="muted">No platform can be scheduled yet, so there is nothing to plan.</p>
      ) : (
        <>
          <p data-testid="runway-summary">
            {scheduledEnd ? (
              <>
                Scheduled through <strong>{shortDay(scheduledEnd)}</strong>.{' '}
              </>
            ) : (
              <>Nothing scheduled from today on. </>
            )}
            {runway.firstGap ? (
              <>
                {gapIsToday ? 'Already empty today' : 'Runs out'} <strong>{shortDay(runway.firstGap)}</strong> on{' '}
                {runway.firstGapPlatforms.map(platformName).join(', ')}.
              </>
            ) : null}
            {projectedEnd ? (
              <span className="block muted">
                Approved videos not yet scheduled could carry posting to {shortDay(projectedEnd)} at one a day; generate a draft below to use them.
              </span>
            ) : episodes ? (
              <span className="block muted">No approved videos are left to schedule; make the next batch before {shortDay(runway.firstGap ?? runway.today)}.</span>
            ) : null}
          </p>
          <div className="table-wrap">
            <table className="runway-table">
              <caption className="sr-only">Per platform: last scheduled day (Through), scheduled posts left (Left), approved videos not yet scheduled there (Spare), and how far those would reach at one a day</caption>
              <thead>
                <tr>
                  <th scope="col">Platform</th>
                  <th scope="col">Through</th>
                  <th scope="col">Left</th>
                  <th scope="col">Spare</th>
                  <th scope="col">Could reach</th>
                </tr>
              </thead>
              <tbody>
                {runway.platforms.map((p) => (
                  <tr key={p.platform} data-testid={`runway-${p.platform}`}>
                    <th scope="row">{platformName(p.platform)}</th>
                    <td>{p.scheduledThrough && p.scheduledThrough >= runway.today ? dayMonth(p.scheduledThrough) : 'None'}</td>
                    <td>{p.postsLeft}</td>
                    <td>{p.spare ?? '…'}</td>
                    <td>{p.couldReach ? dayMonth(p.couldReach) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <ul className="cal-legend" aria-label="Legend">
        <li>
          <span className="cal-dot cal-dot-info" aria-hidden="true" /> Scheduled
        </li>
        <li>
          <span className="cal-dot cal-dot-good" aria-hidden="true" /> Published
        </li>
        <li>
          <span className="cal-dot cal-dot-bad" aria-hidden="true" /> Failed or missed
        </li>
        <li>
          <span className="cal-swatch cal-day-projected" aria-hidden="true" /> Unscheduled videos could fill
        </li>
      </ul>
      {months.map((month) => (
        <div key={month.key} className="stack">
          <h3 className="day-heading">{monthName(month.key)}</h3>
          <table className="cal-grid">
            <caption className="sr-only">{monthName(month.key)}: posts per day</caption>
            <thead>
              <tr>
                {WEEKDAYS.map((d) => (
                  <th key={d} scope="col">
                    {d}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {month.weeks.map((week) => (
                <tr key={week[0]?.dateKey}>
                  {week.map((day) => {
                    if (!day.inMonth) return <td key={day.dateKey} className="cal-out" />
                    const past = day.dateKey < runway.today
                    const projected =
                      !past && !day.posts.length && projectedEnd !== null && day.dateKey <= projectedEnd && (!scheduledEnd || day.dateKey > scheduledEnd)
                    const classes = ['cal-day', past ? 'cal-day-past' : '', day.dateKey === runway.today ? 'cal-day-today' : '', projected ? 'cal-day-projected' : '']
                    return (
                      <td key={day.dateKey}>
                        <button
                          type="button"
                          className={classes.filter(Boolean).join(' ')}
                          aria-pressed={selected === day.dateKey}
                          aria-label={dayLabel(day, projected)}
                          onClick={() => setSelected(selected === day.dateKey ? null : day.dateKey)}
                        >
                          <span className="cal-num">{Number(day.dateKey.slice(8))}</span>
                          <span className="cal-dots" aria-hidden="true">
                            {day.posts.map((j) => (
                              <span key={j.key} className={`cal-dot cal-dot-${jobTone(j)}`} />
                            ))}
                          </span>
                        </button>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
      <div aria-live="polite">
        {selectedDay ? (
          <section className="subcard stack" data-testid="calendar-day">
            <h3 className="h4">{formatDayHeading(selectedDay.dateKey)}</h3>
            {selectedDay.posts.length ? (
              <ul className="stack">
                {selectedDay.posts.map((j) => {
                  const status = ledgerStatus(j.status)
                  return (
                    <li key={j.key}>
                      <strong>{platformName(j.platform)}</strong> {formatTimeLocalAndUtc(j.slotUtc, zone)} · {j.episodeId}{' '}
                      <StatusBadge tone={status.tone} label={j.statusLabel || status.label} />
                    </li>
                  )
                })}
              </ul>
            ) : (
              <p className="muted">Nothing scheduled{selectedDay.dateKey < runway.today ? '' : ` (the queue ends ${scheduledEnd ? shortDay(scheduledEnd) : 'before today'})`}.</p>
            )}
            {selectedDay.posts.length ? (
              <p>
                <a href="#/schedule/queue">Edit in the queue →</a>
              </p>
            ) : null}
          </section>
        ) : (
          <p className="hint">Tap a day to see its posts.</p>
        )}
      </div>
    </section>
  )
}
