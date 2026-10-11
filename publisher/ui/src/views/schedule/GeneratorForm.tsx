import { useState, type FormEvent } from 'react'
import type { ChannelSummary, Platform, ScheduleInputs, Weekday } from '../../api/types'
import { PLATFORMS } from '../../api/types'
import { PROVIDER_DAILY_CAPS } from '../../lib/contract'
import { platformName } from '../../lib/format'
import {
  buildScheduleInputs,
  emptyScheduleForm,
  RECOMMENDED_DAYS,
  recommendedScheduleForm,
  SUGGESTED_TIMEZONE,
  WEEKDAYS,
  type PlatformForm,
  type ScheduleForm,
} from '../../lib/scheduleForm'
import { localDateKey } from '../../lib/time'

export function GeneratorForm({
  channels,
  busy,
  onGenerate,
  initial,
}: {
  channels: ChannelSummary[]
  busy: boolean
  onGenerate: (inputs: ScheduleInputs) => void
  /** Customize opens the form already filled with the recommended plan; without it the form starts empty. */
  initial?: ScheduleForm
}) {
  const [form, setForm] = useState<ScheduleForm>(() => initial ?? emptyScheduleForm())
  const [errors, setErrors] = useState<string[]>([])
  const setPlatform = (p: Platform, change: Partial<PlatformForm>) =>
    setForm((f) => ({ ...f, platforms: { ...f.platforms, [p]: { ...f.platforms[p], ...change } } }))

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const built = buildScheduleInputs(form)
    if (!built.ok) {
      setErrors(built.errors)
      return
    }
    setErrors([])
    onGenerate(built.inputs)
  }

  return (
    <form className="stack" onSubmit={submit} aria-labelledby="gen-h" noValidate data-testid="generator-form">
      <h2 id="gen-h" className="sr-only">
        Customize the draft schedule
      </h2>
      <p className="hint">Every field is editable. The draft is a preview; nothing is queued until you approve it.</p>
      <div className="actions">
        <button
          type="button"
          className="btn"
          onClick={() => {
            const blocked = new Set(channels.filter((c) => c.blockedReason).map((c) => c.platform))
            setForm(recommendedScheduleForm(localDateKey(new Date().toISOString(), SUGGESTED_TIMEZONE), blocked))
            setErrors([])
          }}
        >
          Use recommended schedule
        </button>
      </div>
      <p className="hint">
        Recommended: one video per platform per day for {RECOMMENDED_DAYS} days ({SUGGESTED_TIMEZONE}): Threads 09:00, X 09:30, Bluesky 10:30,
        Facebook 12:15, YouTube 16:00, Instagram 18:00, TikTok 19:00. Blocked platforms are left out. Every field stays editable.
      </p>

      <fieldset className="stack">
        <legend>Timezone and dates</legend>
        <div className="field">
          <label htmlFor="g-tz">Timezone (IANA name)</label>
          <input
            id="g-tz"
            type="text"
            value={form.timezone}
            onChange={(e) => setForm({ ...form, timezone: e.target.value })}
            autoCapitalize="off"
            autoCorrect="off"
            spellCheck={false}
            placeholder="e.g. Europe/London"
          />
          <div className="actions">
            <button type="button" className="btn btn-quiet" onClick={() => setForm({ ...form, timezone: SUGGESTED_TIMEZONE })}>
              Use {SUGGESTED_TIMEZONE}
            </button>
          </div>
        </div>
        <div className="grid-2">
          <div className="field">
            <label htmlFor="g-start">Start date</label>
            <input id="g-start" type="date" value={form.startDate} onChange={(e) => setForm({ ...form, startDate: e.target.value })} />
          </div>
          <div className="field">
            <label htmlFor="g-end">End date</label>
            <input id="g-end" type="date" value={form.endDate} onChange={(e) => setForm({ ...form, endDate: e.target.value })} />
          </div>
        </div>
      </fieldset>

      {PLATFORMS.map((p) => (
        <PlatformFields
          key={p}
          platform={p}
          value={form.platforms[p]}
          channel={channels.find((c) => c.platform === p) ?? null}
          onChange={(change) => setPlatform(p, change)}
        />
      ))}

      <fieldset className="stack">
        <legend>Across platforms</legend>
        <div className="grid-2">
          <div className="field">
            <label htmlFor="g-stagger">Stagger for the same video (minutes, 0 = none)</label>
            <input
              id="g-stagger"
              type="number"
              inputMode="numeric"
              min={0}
              step={1}
              value={form.staggerMinutes}
              onChange={(e) => setForm({ ...form, staggerMinutes: e.target.value })}
            />
          </div>
          <div className="field">
            <label htmlFor="g-order">Content ordering</label>
            <select id="g-order" value={form.ordering} onChange={(e) => setForm({ ...form, ordering: e.target.value as ScheduleForm['ordering'] })}>
              <option value="game-round-robin">Game round-robin (scalar → continuum → whenabouts → tectonic), interleaved difficulty</option>
            </select>
          </div>
        </div>
        <div className="field-check">
          <input id="g-fc" type="checkbox" checked={form.firstComment} onChange={(e) => setForm({ ...form, firstComment: e.target.checked })} />
          <label htmlFor="g-fc">Add own first comments/replies where a route exists (Instagram, Threads, Bluesky; X as thread item 2)</label>
        </div>
        <div className="field-check">
          <input id="g-ar" type="checkbox" checked={form.answerReply} onChange={(e) => setForm({ ...form, answerReply: e.target.checked })} />
          <label htmlFor="g-ar">Add delayed answer replies where the episode has one (Instagram, Threads, Bluesky)</label>
        </div>
        <details>
          <summary>Provider daily caps applied by the generator</summary>
          <ul>
            {PROVIDER_DAILY_CAPS.map((c) => (
              <li key={c.label}>
                {c.label}: {c.limit} per day
              </li>
            ))}
          </ul>
        </details>
      </fieldset>

      {errors.length ? (
        <div className="notice notice-error" role="alert">
          <p>
            <strong>Complete these first:</strong>
          </p>
          <ul>
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="actions">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? 'Generating…' : 'Generate draft'}
        </button>
      </div>
    </form>
  )
}

function PlatformFields({
  platform,
  value,
  channel,
  onChange,
}: {
  platform: Platform
  value: PlatformForm
  channel: ChannelSummary | null
  onChange: (change: Partial<PlatformForm>) => void
}) {
  const [time, setTime] = useState('')
  const name = platformName(platform)
  const id = `g-${platform}`
  const addTime = () => {
    if (/^([01]\d|2[0-3]):[0-5]\d$/.test(time) && !value.times.includes(time)) onChange({ times: [...value.times, time].sort() })
    setTime('')
  }
  const toggleDay = (day: Weekday, on: boolean) =>
    onChange({ weekdays: on ? [...value.weekdays, day].sort((a, b) => a - b) : value.weekdays.filter((d) => d !== day) })
  return (
    <fieldset className="stack platform-fieldset">
      <legend>{name}</legend>
      {channel?.blockedReason ? <p className="notice notice-warn">Will be excluded: {channel.blockedReason}</p> : null}
      <div className="field-check">
        <input id={`${id}-inc`} type="checkbox" checked={value.include} onChange={(e) => onChange({ include: e.target.checked })} />
        <label htmlFor={`${id}-inc`}>Include {name}</label>
      </div>
      {value.include ? (
        <>
          <fieldset>
            <legend className="sublegend">Weekdays</legend>
            <div className="chip-row">
              {WEEKDAYS.map((d) => (
                <div className="field-check chip" key={d.value}>
                  <input
                    id={`${id}-d${d.value}`}
                    type="checkbox"
                    checked={value.weekdays.includes(d.value)}
                    onChange={(e) => toggleDay(d.value, e.target.checked)}
                  />
                  <label htmlFor={`${id}-d${d.value}`}>
                    <span aria-hidden="true">{d.short}</span>
                    <span className="sr-only">{d.long}</span>
                  </label>
                </div>
              ))}
            </div>
          </fieldset>
          <div className="field">
            <label htmlFor={`${id}-time`}>Add a posting time (24-hour, local)</label>
            <div className="inline">
              <input id={`${id}-time`} type="time" value={time} onChange={(e) => setTime(e.target.value)} />
              <button type="button" className="btn" onClick={addTime}>
                Add time
              </button>
            </div>
            {value.times.length ? (
              <ul className="chip-row" aria-label={`${name} times`}>
                {value.times.map((t) => (
                  <li key={t} className="chip">
                    <span>{t}</span>
                    <button type="button" className="btn btn-quiet" onClick={() => onChange({ times: value.times.filter((x) => x !== t) })}>
                      Remove {t}
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="hint">No times yet.</p>
            )}
          </div>
          <div className="grid-2">
            <div className="field">
              <label htmlFor={`${id}-max`}>Max posts per day</label>
              <input id={`${id}-max`} type="number" inputMode="numeric" min={1} step={1} value={value.maxPerDay} onChange={(e) => onChange({ maxPerDay: e.target.value })} />
            </div>
            <div className="field">
              <label htmlFor={`${id}-gap`}>Minimum gap on this account (hours)</label>
              <input id={`${id}-gap`} type="number" inputMode="decimal" min={0} step={0.5} value={value.minGapHours} onChange={(e) => onChange({ minGapHours: e.target.value })} />
            </div>
          </div>
        </>
      ) : null}
    </fieldset>
  )
}
