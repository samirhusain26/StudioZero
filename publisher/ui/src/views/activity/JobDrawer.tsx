import { api } from '../../api/client'
import type { JobDetailResponse } from '../../api/types'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Loading } from '../../components/Loading'
import { Modal } from '../../components/Modal'
import { StatusBadge } from '../../components/StatusBadge'
import { Time } from '../../components/Time'
import { useApi } from '../../hooks/useApi'
import { platformName, shortHash } from '../../lib/format'
import { ledgerStatus } from '../../lib/labels'

export function JobDrawer({ jobId, onClose }: { jobId: string; onClose: () => void }) {
  const { data, error, loading } = useApi(() => api.job(jobId), jobId)
  return (
    <Modal title={`Job ${shortHash(jobId)}`} onClose={onClose} variant="drawer">
      {loading && !data ? <Loading /> : null}
      <ErrorNotice error={error} title="Job unavailable" />
      {data ? <JobDetail data={data} /> : null}
    </Modal>
  )
}

export function JobDetail({ data }: { data: JobDetailResponse }) {
  const zone = data.displayTimezone
  const job = data.job
  const status = ledgerStatus(job.status)
  return (
    <div className="stack">
      <p className="row-head">
        <strong>{platformName(job.platform)}</strong> <StatusBadge tone={status.tone} label={job.statusLabel || status.label} />
      </p>
      <dl className="facts">
        <dt>Slot</dt>
        <dd>
          <Time iso={job.slotUtc} zone={zone} />
        </dd>
        <dt>Dispatched</dt>
        <dd>
          <Time iso={job.dispatchedAt} zone={zone} />
        </dd>
        <dt>Published</dt>
        <dd>
          <Time iso={job.publishedAt} zone={zone} />
        </dd>
        <dt>Episode</dt>
        <dd>
          <code>{job.episode}</code>
        </dd>
        <dt>Attempts</dt>
        <dd>{job.attempts}</dd>
        <dt>Manifest</dt>
        <dd>{data.manifestSha256 ? <code>{shortHash(data.manifestSha256, 12)}</code> : '—'}</dd>
      </dl>
      {job.permalink ? (
        <p>
          <a href={job.permalink} target="_blank" rel="noopener noreferrer">
            Confirmed permalink
          </a>
        </p>
      ) : null}
      {job.error ? (
        <div className="notice notice-warn">
          <p>
            <strong>{job.error.title}.</strong> {job.error.detail}
          </p>
          {job.error.nextAction ? (
            <p>
              <strong>Next step:</strong> {job.error.nextAction}
            </p>
          ) : null}
        </div>
      ) : null}
      {data.reconciliation ? (
        <div className="notice notice-info">
          <p>
            <strong>{data.reconciliation.label}.</strong> This job is never sent again from here.
          </p>
          <p>
            Last check <Time iso={data.reconciliation.lastCheckAt} zone={zone} />; next check <Time iso={data.reconciliation.nextCheckAt} zone={zone} />.
          </p>
          <ol className="steps">
            {data.reconciliation.ownerActions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ol>
        </div>
      ) : null}
      <h3>Published text</h3>
      <p className="exact-text">{data.payload.caption}</p>
      {data.payload.youtube ? (
        <p className="exact-text">
          {data.payload.youtube.title}
          {'\n\n'}
          {data.payload.youtube.description}
        </p>
      ) : null}
      {data.payload.thread?.map((t, i) => (
        <p key={`th${i}`} className="exact-text">
          Thread item {i + 2}: {t}
        </p>
      ))}
      {data.payload.mediaSha256 ? (
        <p className="muted">
          Media <code>{shortHash(data.payload.mediaSha256, 12)}</code>
          {data.payload.mediaUrl ? ` · ${data.payload.mediaUrl}` : ''}
        </p>
      ) : null}
      <h3>Events</h3>
      <ol className="timeline">
        {data.events.map((e) => (
          <li key={e.seq}>
            <Time iso={e.at} zone={zone} /> — <strong>{e.label || e.kind}</strong>
            {e.detail ? `: ${e.detail}` : ''}
          </li>
        ))}
      </ol>
    </div>
  )
}
