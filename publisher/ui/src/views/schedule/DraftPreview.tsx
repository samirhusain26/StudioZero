import { useState } from 'react'
import type { DraftJob, DraftResponse, Platform } from '../../api/types'
import { ConfirmDialog } from '../../components/Modal'
import { StatusBadge } from '../../components/StatusBadge'
import { TextCounterField } from '../../components/TextCounterField'
import { CAPTION_LIMITS, COMMENT_LIMITS, counter, textLength, utf8Bytes, YOUTUBE_DESCRIPTION_BYTES, type CounterState } from '../../lib/contract'
import { platformName, shortHash, titleCase } from '../../lib/format'
import { fillSummary, groupDraftJobs } from '../../lib/scheduleForm'
import { formatDayHeading, formatLocalAndUtc } from '../../lib/time'

export function editCounter(job: Pick<DraftJob, 'platform' | 'kind'>, text: string): CounterState {
  const p = job.platform
  if (p === 'youtube') return counter(utf8Bytes(text), YOUTUBE_DESCRIPTION_BYTES)
  if (job.kind !== 'post' && p in COMMENT_LIMITS) return counter(textLength(p, text), COMMENT_LIMITS[p as keyof typeof COMMENT_LIMITS])
  return counter(textLength(p, text), CAPTION_LIMITS[p as Exclude<Platform, 'youtube'>])
}

export function DraftPreview({
  draft,
  previousSha,
  busy,
  onEdit,
  onRemove,
  onRegenerate,
}: {
  draft: DraftResponse
  previousSha: string | null
  busy: boolean
  onEdit: (key: string, text: string) => void
  onRemove: (key: string) => void
  onRegenerate: () => void
}) {
  const d = draft.draft
  const zone = d.inputs.timezone
  const days = groupDraftJobs(d.jobs, zone)
  const [removing, setRemoving] = useState<DraftJob | null>(null)
  return (
    <section className="card stack" aria-labelledby="draft-h" data-testid="draft-preview">
      <h2 id="draft-h">Draft {shortHash(draft.sha256)}</h2>
      <p aria-live="polite">
        <StatusBadge tone={draft.status === 'draft' ? 'info' : draft.status === 'failed' ? 'bad' : 'neutral'} label={titleCase(draft.status)} />{' '}
        {previousSha ? (
          <span>
            New draft hash <code>{shortHash(draft.sha256)}</code> (was <code>{shortHash(previousSha)}</code>).
          </span>
        ) : null}
      </p>
      <details>
        <summary>Full draft hash</summary>
        <code className="break">{draft.sha256}</code>
      </details>
      <p className="summary-line" data-testid="draft-summary">
        <strong>{fillSummary(d)}</strong>; {d.summary.companions} companion job{d.summary.companions === 1 ? '' : 's'}. Times shown in {zone} and UTC.
      </p>
      {d.baseManifestSha256 ? (
        <p className="hint">
          Builds on the approved manifest <code>{shortHash(d.baseManifestSha256)}</code>; its jobs are carried unchanged and marked “Carried”.
        </p>
      ) : null}

      {draft.blockingProblems.length ? (
        <div className="notice notice-error" role="alert">
          <p>
            <strong>Blocking problems — this draft cannot be approved:</strong>
          </p>
          <ul>
            {draft.blockingProblems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {d.warnings.length ? (
        <div className="notice notice-warn">
          <p>
            <strong>Warnings</strong>
          </p>
          <ul>
            {d.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {d.excluded.length ? (
        <div>
          <h3>Excluded platforms</h3>
          <ul>
            {d.excluded.map((e) => (
              <li key={e.platform}>
                <strong>{platformName(e.platform)}</strong>: {e.reason}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {d.unfilled.length ? (
        <details>
          <summary>
            Unfilled slots ({d.unfilled.length})
          </summary>
          <ul>
            {d.unfilled.map((u) => (
              <li key={`${u.platform}-${u.slotLocal}`}>
                {platformName(u.platform)} — {u.slotUtc ? formatLocalAndUtc(u.slotUtc, zone) : `${u.slotLocal} (does not exist locally)`}: {u.reason}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <div className="actions">
        <button type="button" className="btn" onClick={onRegenerate} disabled={busy}>
          Regenerate (same inputs and edits)
        </button>
      </div>

      {days.length === 0 ? <p>No jobs in this draft.</p> : null}
      {days.map((day) => (
        <section key={day.dateKey} aria-labelledby={`day-${day.dateKey}`} className="stack">
          <h3 id={`day-${day.dateKey}`} className="day-heading">
            {formatDayHeading(day.dateKey)}
          </h3>
          <ul className="stack">
            {day.items.map(({ job, companions }) => (
              <li key={job.key} className="subcard job">
                <JobView
                  job={job}
                  zone={zone}
                  coverUrl={job.coverSha256 ? (draft.coverUrls[job.coverSha256] ?? null) : null}
                  edited={job.key in d.inputs.edits}
                  busy={busy}
                  onEdit={onEdit}
                  onRemove={() => setRemoving(job)}
                />
                {companions.length ? (
                  <ul className="companions" aria-label="Companion jobs">
                    {companions.map((c) => (
                      <li key={c.key} className="subcard companion">
                        <JobView
                          job={c}
                          zone={zone}
                          coverUrl={null}
                          edited={c.key in d.inputs.edits}
                          busy={busy}
                          onEdit={onEdit}
                          onRemove={() => setRemoving(c)}
                        />
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ))}
      {removing ? (
        <ConfirmDialog
          title="Remove this job from the draft?"
          confirmLabel="Remove and make a new draft"
          danger
          busy={busy}
          onCancel={() => setRemoving(null)}
          onConfirm={() => {
            onRemove(removing.key)
            setRemoving(null)
          }}
        >
          <p>
            {platformName(removing.platform)} {removing.kind} for <code>{removing.episodeKey}</code> at {formatLocalAndUtc(removing.slotUtc, zone)}.
          </p>
          <p>This produces a new draft with a new hash. Companion jobs of a removed post are removed with it.</p>
        </ConfirmDialog>
      ) : null}
    </section>
  )
}

function JobView({
  job,
  zone,
  coverUrl,
  edited,
  busy,
  onEdit,
  onRemove,
}: {
  job: DraftJob
  zone: string
  coverUrl: string | null
  edited: boolean
  busy: boolean
  onEdit: (key: string, text: string) => void
  onRemove: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(job.text)
  const c = editCounter(job, text)
  return (
    <article aria-label={`${platformName(job.platform)} ${job.kind} ${job.episodeKey}`}>
      <p className="row-head">
        <time dateTime={job.slotUtc} className="job-time" data-testid="job-time">
          {formatLocalAndUtc(job.slotUtc, zone)}
        </time>
      </p>
      <p className="row-head">
        <strong>{platformName(job.platform)}</strong> <span className="muted">account {job.accountId}</span>{' '}
        <StatusBadge tone="neutral" label={titleCase(job.kind)} />
        {job.carried ? <StatusBadge tone="info" label="Carried from approved manifest" /> : null}
        {edited ? <StatusBadge tone="warn" label="Edited" /> : null}
      </p>
      <div className="job-body">
        {coverUrl ? <img className="thumb" src={coverUrl} alt={`Cover for ${job.episodeId}`} width={54} height={96} loading="lazy" /> : null}
        <p className="muted">
          {job.episodeId} rev {job.revision} · <code>{job.episodeKey}</code>
          {job.videoSha256 ? (
            <>
              {' '}
              · video <code>{shortHash(job.videoSha256)}</code>
            </>
          ) : null}
          {job.coverSha256 ? (
            <>
              {' '}
              · cover <code>{shortHash(job.coverSha256)}</code>
            </>
          ) : null}
        </p>
      </div>
      {job.youtube ? (
        <dl className="text-list">
          <div>
            <dt>YouTube title</dt>
            <dd className="exact-text">{job.youtube.title}</dd>
          </div>
          <div>
            <dt>YouTube description</dt>
            <dd className="exact-text">{job.youtube.description}</dd>
          </div>
        </dl>
      ) : null}
      <dl className="text-list">
        <div>
          <dt>{job.kind === 'post' ? 'Exact caption' : 'Exact text'}</dt>
          <dd className="exact-text">{job.text}</dd>
        </div>
        {job.thread
          ? job.thread.map((item, i) => (
              <div key={`t${i}`}>
                <dt>X thread item {i + 2}</dt>
                <dd className="exact-text">{item}</dd>
              </div>
            ))
          : null}
        {job.poll ? (
          <div>
            <dt>Poll</dt>
            <dd className="exact-text">
              {job.poll.question}
              {'\n'}
              {job.poll.options.map((o, i) => `${'ABCD'[i]}) ${o}`).join('\n')}
            </dd>
          </div>
        ) : null}
      </dl>
      {job.warnings.length ? (
        <ul className="problem-list">
          {job.warnings.map((w) => (
            <li key={w}>Warning: {w}</li>
          ))}
        </ul>
      ) : null}
      {job.carried ? (
        <p className="hint">Carried jobs are changed from the approved queue, not here.</p>
      ) : editing ? (
        <div className="stack">
          <TextCounterField label="New text" value={text} onChange={setText} counter={c} rows={5} />
          <div className="actions">
            <button type="button" className="btn" onClick={() => { setEditing(false); setText(job.text) }}>
              Cancel edit
            </button>
            <button type="button" className="btn btn-primary" disabled={busy || c.over || !text.trim() || text === job.text} onClick={() => onEdit(job.key, text)}>
              Save as new draft
            </button>
          </div>
        </div>
      ) : (
        <div className="actions">
          <button type="button" className="btn" onClick={() => setEditing(true)} disabled={busy}>
            Edit text
          </button>
          <button type="button" className="btn btn-danger" onClick={onRemove} disabled={busy}>
            Remove
          </button>
        </div>
      )}
    </article>
  )
}
