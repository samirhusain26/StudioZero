import { useId, useState } from 'react'
import type { CatalogManualProject } from '../../api/types'
import { CopyBlock } from '../../components/CopyBlock'
import { daysUntil, fillPrompt, isoWeek } from '../../lib/manualProject'
import { formatDayHeading } from '../../lib/time'

function countdown(days: number): string {
  if (days > 1) return `${days} days to go`
  if (days === 1) return 'tomorrow'
  if (days === 0) return 'today'
  return 'done'
}

/**
 * Studio › Overview: a project made here but posted by hand (studio.json manualProjects). The Pi never sees its files,
 * so the card only says what to bring and gives the prompts to paste into Claude Code on the Mac.
 */
export function ManualProjectCard({ project, now = new Date() }: { project: CatalogManualProject; now?: Date }) {
  const id = useId()
  const [lastWeek, setLastWeek] = useState(false)
  const current = isoWeek(now)
  const previous = isoWeek(now, -1)
  const week = lastWeek ? previous : current
  const weekly = project.prompts.some((p) => p.template.includes('{'))
  const named = project.accounts.filter((a) => a.handle)
  return (
    <section className="card stack" aria-labelledby={`studio-${project.id}`} data-testid="studio-manual-project">
      <h2 id={`studio-${project.id}`}>
        {project.name} <span className="muted">· posted by hand</span>
      </h2>
      <p>{project.summary}</p>
      <dl className="facts">
        <dt>Cadence</dt>
        <dd>{project.cadence}</dd>
        {project.goal ? (
          <>
            <dt>Goal</dt>
            <dd>
              {project.goal.name}, {formatDayHeading(project.goal.date)} · {countdown(daysUntil(now, project.goal.date))}
              {project.goal.note ? <span className="muted"> ({project.goal.note})</span> : null}
            </dd>
          </>
        ) : null}
        <dt>Accounts</dt>
        <dd>
          {named.length
            ? named.map((a) => `${a.platform} ${a.handle}`).join(' · ')
            : `${project.accounts.map((a) => a.platform).join(', ')}: not named yet`}
        </dd>
        <dt>Publishing</dt>
        <dd>You post it. No batches, schedule or autopilot; its files stay on the Mac.</dd>
      </dl>
      {project.bring.length ? (
        <div className="stack">
          <h3 className="h4">Bring to the session</h3>
          <ul className="compact-list">
            {project.bring.map((b) => (
              <li key={b}>{b}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {weekly ? (
        <div className="field">
          <label htmlFor={`${id}-week`}>Week</label>
          <select id={`${id}-week`} value={lastWeek ? 'last' : 'this'} onChange={(e) => setLastWeek(e.target.value === 'last')}>
            <option value="this">
              This week: {current.id} ({current.monday} to {current.sunday})
            </option>
            <option value="last">
              Last week: {previous.id} ({previous.monday} to {previous.sunday})
            </option>
          </select>
        </div>
      ) : null}
      {project.prompts.map((p) => (
        <CopyBlock key={p.id} label={`${p.label} · paste into Claude Code in StudioZero on the Mac`} code={fillPrompt(p.template, week)} button="Copy prompt" />
      ))}
    </section>
  )
}
