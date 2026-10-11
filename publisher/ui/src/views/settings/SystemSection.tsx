import { api } from '../../api/client'
import type { DashboardResponse, UncertainJob } from '../../api/types'
import { ErrorNotice } from '../../components/ErrorNotice'
import { StatusBadge } from '../../components/StatusBadge'
import { Time } from '../../components/Time'
import { useApi } from '../../hooks/useApi'
import { formatBytes, platformName } from '../../lib/format'
import { ledgerStatus, SEVERITY } from '../../lib/labels'
import { outcomeTone, outcomeWords, triggerWords } from '../../lib/metricsStatus'

/** Settings › System: diagnostics only (timers, monitor, budgets, storage, issues, jobs needing reconciliation). */
export function SystemSection({ data }: { data: DashboardResponse }) {
  const zone = data.displayTimezone
  const attention = data.issues.length + data.uncertainJobs.length
  return (
    <section className="card stack" aria-labelledby="system-h" data-testid="system-section">
      <h2 id="system-h">System</h2>
      <p className="hint">
        {attention ? `${attention} item${attention === 1 ? '' : 's'} need attention; they are open below.` : 'Nothing reported. Details are collapsed below.'}{' '}
        Updated <Time iso={data.generatedAt} zone={zone} />
      </p>
      <details className="disclosure" open={data.uncertainJobs.length > 0}>
        <summary>Jobs needing reconciliation ({data.uncertainJobs.length})</summary>
        <UncertainJobs jobs={data.uncertainJobs} zone={zone} />
      </details>
      <details className="disclosure" open={data.issues.length > 0}>
        <summary>Issues ({data.issues.length})</summary>
        <IssuesList data={data} />
      </details>
      <details className="disclosure">
        <summary>Timers</summary>
        <TimersBlock data={data} />
      </details>
      <PostStatsSystem zone={zone} />
      <details className="disclosure">
        <summary>Health, budgets and storage</summary>
        <HealthBlock data={data} />
      </details>
    </section>
  )
}

export function UncertainJobs({ jobs, zone }: { jobs: UncertainJob[]; zone: string }) {
  return (
    <section className="stack" aria-labelledby="uncertain-h" data-testid="uncertain-jobs">
      <h3 id="uncertain-h" className="sr-only">Jobs needing reconciliation</h3>
      <p className="hint">
        These may already be public. They are never sent again from here: the publisher keeps checking, and the owner resolves them with
        evidence.
      </p>
      {jobs.length === 0 ? (
        <p>None.</p>
      ) : (
        <ul className="stack">
          {jobs.map((job) => {
            const status = ledgerStatus(job.status)
            return (
              <li key={job.jobId} className="subcard">
                <p className="row-head">
                  <strong>{platformName(job.platform)}</strong> <code>{job.episode}</code>{' '}
                  <StatusBadge tone={status.tone} label={job.reconciliation.label || status.label} />
                </p>
                <dl className="facts">
                  <dt>State</dt>
                  <dd>{status.label}</dd>
                  <dt>Slot</dt>
                  <dd>
                    <Time iso={job.slotUtc} zone={zone} />
                  </dd>
                  <dt>Last check</dt>
                  <dd>
                    <Time iso={job.reconciliation.lastCheckAt} zone={zone} />
                  </dd>
                  <dt>Next check</dt>
                  <dd>
                    <Time iso={job.reconciliation.nextCheckAt} zone={zone} />
                  </dd>
                  <dt>Account</dt>
                  <dd>
                    <code>{job.accountId}</code>
                  </dd>
                </dl>
                {job.error ? (
                  <p>
                    <strong>{job.error.title}.</strong> {job.error.detail}
                  </p>
                ) : null}
                <h3 className="h4">Owner actions</h3>
                <ol className="steps">
                  {job.reconciliation.ownerActions.map((action) => (
                    <li key={action}>{action}</li>
                  ))}
                </ol>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

function IssuesList({ data }: { data: DashboardResponse }) {
  return (
    <section className="stack" aria-labelledby="issues-h">
      <h3 id="issues-h" className="sr-only">Issues</h3>
      {data.issues.length === 0 ? (
        <p>No issues reported.</p>
      ) : (
        <ul className="stack">
          {data.issues.map((issue) => {
            const severity = SEVERITY[issue.severity]
            return (
              <li key={issue.id} className="subcard">
                <p className="row-head">
                  <StatusBadge tone={severity.tone} label={severity.label} /> <strong>{issue.title}</strong>
                  {issue.platform ? <span className="muted"> · {platformName(issue.platform)}</span> : null}
                </p>
                <p>{issue.detail}</p>
                {issue.nextAction ? (
                  <p>
                    <strong>Next step:</strong> {issue.nextAction}
                  </p>
                ) : null}
                {issue.at ? (
                  <p className="muted">
                    <Time iso={issue.at} zone={data.displayTimezone} />
                  </p>
                ) : null}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

function TimersBlock({ data }: { data: DashboardResponse }) {
  return (
    <section className="stack" aria-labelledby="timers-h">
      <h3 id="timers-h" className="sr-only">Timers</h3>
      <ul className="stack">
        {data.timers.map((t) => (
          <li key={t.unit} className="subcard">
            <p className="row-head">
              <strong>{t.label}</strong> <code className="muted">{t.unit}</code>
            </p>
            <p>
              <StatusBadge tone={t.enabled ? 'info' : 'neutral'} label={t.enabled ? 'Enabled' : 'Disabled'} />{' '}
              <StatusBadge tone={t.active ? 'info' : 'neutral'} label={t.active ? 'Active' : 'Inactive'} />{' '}
              <StatusBadge
                tone={t.lastResult === 'success' ? 'good' : t.lastResult === 'failed' ? 'bad' : 'neutral'}
                label={`Last result: ${t.lastResult === 'never' ? 'never run' : t.lastResult}`}
              />
            </p>
            <dl className="facts">
              <dt>Last run</dt>
              <dd>
                <Time iso={t.lastRunAt} zone={data.displayTimezone} />
              </dd>
              <dt>Next run</dt>
              <dd>
                <Time iso={t.nextRunAt} zone={data.displayTimezone} />
              </dd>
              {t.lastResultDetail ? (
                <>
                  <dt>Detail</dt>
                  <dd>{t.lastResultDetail}</dd>
                </>
              ) : null}
            </dl>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** Hourly post stats reads (GET /api/metrics/status): state only; the controls live in Library › Make a batch. */
export function PostStatsSystem({ zone }: { zone: string }) {
  const { data, error } = useApi(api.getMetricsStatus)
  const run = data?.lastRun ?? null
  return (
    <details className="disclosure" data-testid="post-stats-system">
      <summary>Post stats{data ? `: hourly reads ${data.enabled ? 'on' : 'off'}` : ''}</summary>
      <section className="stack" aria-labelledby="post-stats-system-h">
        <h3 id="post-stats-system-h" className="sr-only">
          Post stats
        </h3>
        <ErrorNotice error={error} title="Post stats status unavailable" />
        {data ? (
          <dl className="facts">
            <dt>Hourly reads</dt>
            <dd>{data.enabled ? 'On' : 'Off (the timer still runs, but reads nothing)'}</dd>
            <dt>Last run</dt>
            <dd>
              {run ? (
                <>
                  <Time iso={run.finishedAt} zone={zone} /> · {triggerWords(run)} · <StatusBadge tone={outcomeTone(run.outcome)} label={outcomeWords(run.outcome)} />
                </>
              ) : (
                'never'
              )}
            </dd>
            <dt>Next timer run</dt>
            <dd>{data.timer ? <Time iso={data.timer.nextRunAt} zone={zone} /> : 'timer not installed'}</dd>
            <dt>Read requests</dt>
            <dd>{data.pathActive ? 'picked up (scalar-social-metrics.path is active)' : 'not picked up: scalar-social-metrics.path is not active'}</dd>
            {data.pending ? (
              <>
                <dt>Waiting</dt>
                <dd>
                  a read asked <Time iso={data.pending.requestedAt} zone={zone} />
                </dd>
              </>
            ) : null}
          </dl>
        ) : null}
        <p className="hint">
          Switch hourly reads and ask for a read in <a href="#/library/make">Library › Make a batch</a>, under How the posts did.
        </p>
      </section>
    </details>
  )
}

function HealthBlock({ data }: { data: DashboardResponse }) {
  const { healthJson, monitor } = data.freshness
  const { pages, buffer } = data.budgets
  return (
    <section className="stack" aria-labelledby="health-h">
      <h3 id="health-h" className="sr-only">Health, budgets and storage</h3>
      <dl className="facts">
        <dt>health.json</dt>
        <dd>
          <StatusBadge tone={healthJson.fresh ? 'good' : 'warn'} label={healthJson.fresh ? 'Fresh' : 'Stale'} /> {healthJson.label}
          {healthJson.ok === false ? ' (reports a problem)' : ''}
        </dd>
        <dt>Monitor</dt>
        <dd>
          <StatusBadge tone={monitor.fresh ? 'good' : 'warn'} label={monitor.fresh ? 'Fresh' : 'Stale'} /> {monitor.label}
          {monitor.ok === false ? ' (reports a problem)' : ''}
        </dd>
        <dt>Pages deployments</dt>
        <dd>
          <StatusBadge tone={pages.low ? 'warn' : 'neutral'} label={pages.low ? 'Low' : 'OK'} /> {pages.label} ({pages.window})
        </dd>
        <dt>Buffer calls</dt>
        <dd>
          <StatusBadge tone={buffer.low ? 'warn' : 'neutral'} label={buffer.low ? 'Low' : 'OK'} /> {buffer.label} ({buffer.window})
        </dd>
        <dt>Free storage</dt>
        <dd>
          <StatusBadge tone={data.storage.low ? 'warn' : 'neutral'} label={data.storage.low ? 'Low' : 'OK'} />{' '}
          {formatBytes(data.storage.freeBytes)} free of {formatBytes(data.storage.totalBytes)} (uploads keep{' '}
          {formatBytes(data.storage.reserveBytes)} in reserve)
        </dd>
      </dl>
    </section>
  )
}
