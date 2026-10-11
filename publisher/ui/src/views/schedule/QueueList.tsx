import { useState } from 'react'
import type { QueueJob, ScheduleResponse } from '../../api/types'
import { ConfirmDialog } from '../../components/Modal'
import { StatusBadge } from '../../components/StatusBadge'
import { TextCounterField } from '../../components/TextCounterField'
import { Time } from '../../components/Time'
import { platformName, shortHash, titleCase } from '../../lib/format'
import { ledgerStatus } from '../../lib/labels'
import { formatDayHeading, localDateKey } from '../../lib/time'
import { editCounter } from './DraftPreview'

export function groupQueue(jobs: readonly QueueJob[], zone: string): { dateKey: string; jobs: QueueJob[] }[] {
  const days = new Map<string, QueueJob[]>()
  for (const job of [...jobs].sort((a, b) => (a.slotUtc < b.slotUtc ? -1 : a.slotUtc > b.slotUtc ? 1 : 0))) {
    const key = localDateKey(job.slotUtc, zone)
    days.set(key, [...(days.get(key) ?? []), job])
  }
  return [...days.entries()].map(([dateKey, list]) => ({ dateKey, jobs: list }))
}

export function QueueList({
  schedule,
  busy,
  onCancel,
  onEdit,
}: {
  schedule: ScheduleResponse
  busy: boolean
  onCancel: (keys: string[]) => void
  onEdit: (key: string, text: string) => void
}) {
  const zone = schedule.displayTimezone
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [confirming, setConfirming] = useState(false)
  const manifest = schedule.manifest
  const selectedJobs = schedule.jobs.filter((j) => selected.has(j.key) && j.editable)
  const toggle = (key: string, on: boolean) =>
    setSelected((s) => {
      const next = new Set(s)
      if (on) next.add(key)
      else next.delete(key)
      return next
    })
  return (
    <section className="card stack" aria-labelledby="queue-h" data-testid="approved-queue">
      <h2 id="queue-h">Current approved queue</h2>
      {manifest ? (
        <dl className="facts">
          <dt>Manifest</dt>
          <dd>
            <code>{shortHash(manifest.sha256, 12)}</code> from draft <code>{shortHash(manifest.draftSha256)}</code>
          </dd>
          <dt>Approved</dt>
          <dd>
            <Time iso={manifest.approvedAt} zone={zone} />
          </dd>
          <dt>Scope</dt>
          <dd>{manifest.scope.map(platformName).join(', ') || 'None'}</dd>
          <dt>Bound in config</dt>
          <dd>{manifest.bound ? 'Yes' : 'No (waiting for the bind step)'}</dd>
          <dt>Jobs</dt>
          <dd>{manifest.jobCount}</dd>
        </dl>
      ) : (
        <p>No approved schedule yet. Approve episodes in the Library, then fill in the form below and generate a draft.</p>
      )}
      <p className="hint">
        Cancelling or editing an undispatched job creates a new draft that needs approval. Until then the current approval stands. Dispatched
        jobs are read-only.
      </p>
      {groupQueue(schedule.jobs, zone).map((day) => (
        <section key={day.dateKey} aria-labelledby={`q-${day.dateKey}`} className="stack">
          <h3 id={`q-${day.dateKey}`} className="day-heading">
            {formatDayHeading(day.dateKey)}
          </h3>
          <ul className="stack">
            {day.jobs.map((job) => (
              <QueueRow key={job.key} job={job} zone={zone} busy={busy} selected={selected.has(job.key)} onToggle={toggle} onEdit={onEdit} />
            ))}
          </ul>
        </section>
      ))}
      {schedule.jobs.some((j) => j.editable) ? (
        <div className="actions">
          <button type="button" className="btn btn-danger" disabled={selectedJobs.length === 0 || busy} onClick={() => setConfirming(true)}>
            Cancel selected ({selectedJobs.length})
          </button>
        </div>
      ) : null}
      {confirming ? (
        <ConfirmDialog
          title={`Cancel ${selectedJobs.length} job${selectedJobs.length === 1 ? '' : 's'}?`}
          confirmLabel="Create cancellation draft"
          danger
          busy={busy}
          onCancel={() => setConfirming(false)}
          onConfirm={() => {
            setConfirming(false)
            onCancel(selectedJobs.map((j) => j.key))
            setSelected(new Set())
          }}
        >
          <p>This makes a new draft without these jobs. Nothing changes until that draft is approved; the current approval stands.</p>
          <ul>
            {selectedJobs.map((j) => (
              <li key={j.key}>
                {platformName(j.platform)} {j.kind} <code>{j.episodeKey}</code>
              </li>
            ))}
          </ul>
        </ConfirmDialog>
      ) : null}
    </section>
  )
}

function QueueRow({
  job,
  zone,
  busy,
  selected,
  onToggle,
  onEdit,
}: {
  job: QueueJob
  zone: string
  busy: boolean
  selected: boolean
  onToggle: (key: string, on: boolean) => void
  onEdit: (key: string, text: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(job.text)
  const status = ledgerStatus(job.status)
  const c = editCounter(job, text)
  const checkId = `sel-${job.key}`
  return (
    <li className={`subcard job${job.parentKey ? ' companion' : ''}`} data-testid="queue-job">
      <p className="row-head">
        <Time iso={job.slotUtc} zone={zone} />
      </p>
      <p className="row-head">
        <strong>{platformName(job.platform)}</strong> <StatusBadge tone="neutral" label={titleCase(job.kind)} />{' '}
        <StatusBadge tone={status.tone} label={job.statusLabel || status.label} />
        {!job.editable ? <StatusBadge tone="neutral" label={`Locked: ${job.lockReason ?? 'dispatched, read-only'}`} /> : null}
      </p>
      <p className="muted">
        {job.episodeId} · <code>{job.episodeKey}</code> · account {job.accountId}
      </p>
      <p className="exact-text">{job.text}</p>
      {job.permalink ? (
        <p>
          <a href={job.permalink} target="_blank" rel="noopener noreferrer">
            View published post
          </a>
        </p>
      ) : null}
      {job.error ? (
        <p>
          <strong>{job.error.title}.</strong> {job.error.detail} {job.error.nextAction ? `Next step: ${job.error.nextAction}` : ''}
        </p>
      ) : null}
      {job.editable ? (
        editing ? (
          <div className="stack">
            <TextCounterField label="New text" value={text} onChange={setText} counter={c} rows={5} />
            <div className="actions">
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setEditing(false)
                  setText(job.text)
                }}
              >
                Cancel edit
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy || c.over || !text.trim() || text === job.text}
                onClick={() => {
                  onEdit(job.key, text)
                  setEditing(false)
                }}
              >
                Create edit draft
              </button>
            </div>
          </div>
        ) : (
          <div className="actions">
            <div className="field-check">
              <input id={checkId} type="checkbox" checked={selected} onChange={(e) => onToggle(job.key, e.target.checked)} />
              <label htmlFor={checkId}>Select to cancel</label>
            </div>
            <button type="button" className="btn" onClick={() => setEditing(true)} disabled={busy}>
              Edit text
            </button>
          </div>
        )
      ) : null}
    </li>
  )
}
