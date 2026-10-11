import { useEffect, useId, useRef, useState } from 'react'
import { api, ApiRequestError } from '../../api/client'
import type { MetricsLastRun, MetricsStatus } from '../../api/types'
import { CopyBlock } from '../../components/CopyBlock'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Loading } from '../../components/Loading'
import { StatusBadge } from '../../components/StatusBadge'
import { Time } from '../../components/Time'
import { platformName } from '../../lib/format'
import {
  BACKFILL_MAX,
  enabledLabel,
  METRICS_POLL_MS,
  METRICS_WAIT_MS,
  outcomeTone,
  outcomeWords,
  parseBackfill,
  platformRuns,
  platformTone,
  platformWord,
  readCounts,
  triggerWords,
  YOUTUBE_KEY_COMMAND,
} from '../../lib/metricsStatus'
import { guideHash } from '../../views'

export const STATS_GUIDE_ANCHOR = 'post-and-account-stats'

/**
 * Post stats controls (Library › Make a batch › How the posts did). The UI never reads stats itself: the switch
 * writes the hourly-reads flag and "Read stats now" writes a request file; scalar-social-metrics.{timer,path} do
 * the reads. A pending request is checked every 4 s for up to 5 minutes, then the panel says it is still waiting.
 */
export function PostStatsPanel({ zone, onRead }: { zone: string; onRead?: () => void }) {
  const id = useId()
  const [status, setStatus] = useState<MetricsStatus | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [actionError, setActionError] = useState<unknown>(null)
  const [busy, setBusy] = useState<'toggle' | 'read' | null>(null)
  const [backfillText, setBackfillText] = useState('0')
  const [backfillError, setBackfillError] = useState<string | null>(null)
  const [stillWaiting, setStillWaiting] = useState(false)
  const [finished, setFinished] = useState<string | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const waitingSince = useRef<number | null>(null)
  const alive = useRef(true)
  const tick = useRef<() => void>(() => {})
  const onReadRef = useRef(onRead)

  const clearTimer = () => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
  }

  /** Keep polling while a read is pending and the 5-minute window is open. */
  const scheduleOrGiveUp = () => {
    clearTimer()
    if (waitingSince.current === null) return
    if (Date.now() - waitingSince.current >= METRICS_WAIT_MS) {
      setStillWaiting(true)
      return
    }
    setStillWaiting(false)
    timer.current = setTimeout(() => tick.current(), METRICS_POLL_MS)
  }

  const apply = (next: MetricsStatus) => {
    setStatus(next)
    setLoadError(null)
    if (next.pending) {
      waitingSince.current ??= Date.now()
      scheduleOrGiveUp()
    } else {
      clearTimer()
      setStillWaiting(false)
      if (waitingSince.current !== null) {
        waitingSince.current = null
        // Announced in the live region, so a screen reader hears that the read is over.
        setFinished(next.lastRun ? `Read ${outcomeWords(next.lastRun.outcome)}.` : 'The Pi picked up the read.')
        onReadRef.current?.()
      }
    }
  }

  const refresh = async () => {
    try {
      const next = await api.getMetricsStatus()
      if (alive.current) apply(next)
    } catch (e) {
      if (!alive.current) return
      setLoadError(e)
      scheduleOrGiveUp()
    }
  }

  useEffect(() => {
    tick.current = () => void refresh()
    onReadRef.current = onRead
  })

  useEffect(() => {
    alive.current = true
    tick.current()
    return () => {
      alive.current = false
      if (timer.current) clearTimeout(timer.current)
      timer.current = null
    }
  }, [])

  // aria-disabled rather than disabled while busy, so a focused button keeps keyboard focus.
  const toggle = async () => {
    if (!status || busy !== null) return
    setBusy('toggle')
    setActionError(null)
    try {
      const next = await api.setMetricsEnabled(!status.enabled)
      if (alive.current) apply(next)
    } catch (e) {
      if (alive.current) setActionError(e)
    } finally {
      if (alive.current) setBusy(null)
    }
  }

  const readNow = async () => {
    if (busy !== null || status?.pending) return
    const backfill = parseBackfill(backfillText)
    if (backfill === null) {
      setBackfillError(`Enter a whole number of days from 0 to ${BACKFILL_MAX}.`)
      return
    }
    setBackfillError(null)
    setFinished(null)
    setBusy('read')
    setActionError(null)
    try {
      const next = await api.requestMetricsRead(backfill > 0 ? backfill : undefined)
      if (!alive.current) return
      // A new request opens a fresh 5-minute window; if it was already read, apply() reports it.
      waitingSince.current = Date.now()
      apply(next)
    } catch (e) {
      if (!alive.current) return
      // 409: a read is already waiting (another tab, or an earlier request). Show it and wait for it.
      if (e instanceof ApiRequestError && e.status === 409) await refresh()
      else setActionError(e)
    } finally {
      if (alive.current) setBusy(null)
    }
  }

  const checkAgain = () => {
    waitingSince.current = Date.now()
    setStillWaiting(false)
    void refresh()
  }

  const run = status?.lastRun ?? null
  const youtubeStored = run?.platforms.youtube?.status === 'ok'

  return (
    <section className="stack stats-panel" aria-labelledby={`${id}-h`} data-testid="post-stats">
      <h3 id={`${id}-h`} className="h4">
        Post stats
      </h3>
      {status ? (
        <>
          <div className="actions">
            <button type="button" className="btn" aria-pressed={status.enabled} onClick={() => void toggle()} aria-disabled={busy !== null || undefined}>
              Hourly reads<span aria-hidden="true">: {enabledLabel(status)}</span>
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => void readNow()}
              aria-disabled={busy !== null || status.pending !== null || undefined}
            >
              {busy === 'read' ? 'Asking the Pi…' : 'Read stats now'}
            </button>
          </div>
          <p className="hint">
            {status.enabled
              ? 'The Pi reads new numbers every hour at :20 (1 h, 24 h, 72 h, 7 days and 30 days after each post).'
              : 'Hourly reads are off: the Pi reads nothing on its own. Read stats now still works.'}
          </p>
          <details className="disclosure">
            <summary>Also read past days</summary>
            <div className="field">
              <label htmlFor={`${id}-backfill`}>
                Also read past days (0–{BACKFILL_MAX})
              </label>
              <input
                id={`${id}-backfill`}
                type="number"
                inputMode="numeric"
                min={0}
                max={BACKFILL_MAX}
                step={1}
                value={backfillText}
                aria-invalid={backfillError ? true : undefined}
                aria-describedby={`${id}-backfill-hint`}
                onChange={(e) => {
                  setBackfillText(e.target.value)
                  setBackfillError(null)
                }}
                className="backfill-input"
              />
            </div>
            <p id={`${id}-backfill-hint`} className="hint">
              With Read stats now, the Pi also fills in account day totals for up to that many past days, where the platform keeps them. Posts are read at their usual checkpoints. 0 reads only what is due.
            </p>
            {backfillError ? (
              <p className="notice notice-error" role="alert">
                {backfillError}
              </p>
            ) : null}
          </details>
          <div role="status" aria-live="polite">
            {finished && !status.pending ? <p className="muted">{finished}</p> : null}
            {status.pending && !stillWaiting ? (
              <p>
                <strong>Waiting for the Pi…</strong>{' '}
                <span className="muted">
                  Asked <Time iso={status.pending.requestedAt} zone={zone} />
                  {status.pending.backfill > 0 ? `, also past ${status.pending.backfill} day${status.pending.backfill === 1 ? '' : 's'}` : ''}.
                </span>
              </p>
            ) : null}
            {status.pending && stillWaiting ? (
              <p className="notice notice-warn">
                Still waiting for the Pi. It reads requests when scalar-social-metrics.path is installed; see{' '}
                <a href={guideHash(STATS_GUIDE_ANCHOR)}>Guide › Post and account stats</a>.
              </p>
            ) : null}
          </div>
          {status.pending && stillWaiting ? (
            <div className="actions">
              <button type="button" className="btn btn-quiet" onClick={checkAgain}>
                Check again
              </button>
            </div>
          ) : null}
          {status.pathActive ? null : (
            <p className="notice notice-warn">
              The Pi is not picking up read requests right now: scalar-social-metrics.path is not active. Hourly reads are not affected.{' '}
              <a href={guideHash(STATS_GUIDE_ANCHOR)}>How to install it</a>
            </p>
          )}
          <LastRun run={run} zone={zone} />
          {youtubeStored ? (
            <p className="hint">YouTube key: already stored.</p>
          ) : (
            <div className="stack">
              <p className="hint">YouTube needs its own API key before the Pi can read its stats. Store it once, on the Pi (owner, sudo):</p>
              <CopyBlock label="On the Pi" code={YOUTUBE_KEY_COMMAND} />
            </div>
          )}
        </>
      ) : loadError ? null : (
        <Loading />
      )}
      <ErrorNotice error={status ? null : loadError} title="Post stats unavailable" />
      <ErrorNotice error={actionError} title="Post stats" />
    </section>
  )
}

function LastRun({ run, zone }: { run: MetricsLastRun | null; zone: string }) {
  if (!run) return <p className="muted">No stats read yet.</p>
  const platforms = platformRuns(run)
  return (
    <div className="stack">
      <p>
        Last read <Time iso={run.finishedAt} zone={zone} /> · {triggerWords(run)} ·{' '}
        <StatusBadge tone={outcomeTone(run.outcome)} label={outcomeWords(run.outcome)} />
      </p>
      {platforms.length ? (
        <ul className="compact-list stats-platforms" aria-label="Each platform in the last read">
          {platforms.map(([platform, r]) => {
            const counts = readCounts(r)
            return (
              <li key={platform}>
                {platformName(platform)}: <StatusBadge tone={platformTone(r)} label={platformWord(r)} />
                {counts ? <span className="muted"> · {counts}</span> : null}
              </li>
            )
          })}
        </ul>
      ) : null}
    </div>
  )
}
