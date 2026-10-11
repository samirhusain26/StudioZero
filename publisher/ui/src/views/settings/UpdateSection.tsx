import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { api, ApiRequestError } from '../../api/client'
import type { UpdateInfo } from '../../api/types'
import { CopyBlock } from '../../components/CopyBlock'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Loading } from '../../components/Loading'
import { ConfirmDialog } from '../../components/Modal'
import { ScreenHelp } from '../../components/ScreenHelp'
import { StatusBadge } from '../../components/StatusBadge'
import { Time } from '../../components/Time'
import { shortHash } from '../../lib/format'
import { deviceTimeZone } from '../../lib/time'
import {
  CHECK_TIMEOUT_MS,
  checkMarker,
  checkProblems,
  changedWords,
  checkSettled,
  clearBaseline,
  DEFAULT_APPLY_UNITS_COMMAND,
  phaseWords,
  pollMode,
  readBaseline,
  startGate,
  UPDATE_POLL_MS,
  UPDATED_KEY,
  unitsApplyState,
  watchOutcome,
  writeBaseline,
  type CheckMarker,
  type UpdateBaseline,
  type WatchOutcome,
} from '../../lib/update'
import { guideHash } from '../../views'

/** A restarting server answers with a network error or a gateway error (Tailscale Serve → 502). */
function unreachable(error: unknown): boolean {
  return error instanceof ApiRequestError && (error.status === 0 || error.status >= 500)
}

function takeUpdatedNotice(): string | null {
  try {
    const commit = sessionStorage.getItem(UPDATED_KEY)
    if (!commit) return null
    sessionStorage.removeItem(UPDATED_KEY)
    return commit
  } catch {
    return null
  }
}

export function UpdateSection({ reloadPage = () => window.location.reload() }: { reloadPage?: () => void }) {
  const id = useId()
  const zone = deviceTimeZone()
  const [info, setInfo] = useState<UpdateInfo | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const [reachable, setReachable] = useState(true)
  const [now, setNow] = useState(() => Date.now())
  const [baseline, setBaseline] = useState<UpdateBaseline | null>(() => readBaseline())
  const [checkPending, setCheckPending] = useState<{ marker: CheckMarker; since: number } | null>(null)
  const [outcome, setOutcome] = useState<WatchOutcome | null>(null)
  const [actionError, setActionError] = useState<unknown>(null)
  const [checkTimedOut, setCheckTimedOut] = useState(false)
  const [updated] = useState(takeUpdatedNotice)
  const [confirming, setConfirming] = useState(false)
  const [confirmSha, setConfirmSha] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (!confirming) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [confirming])

  const fetchStatus = useCallback(
    (): Promise<{ info: UpdateInfo | null; reachable: boolean; at: number }> =>
      api.updateStatus().then(
        (next) => {
          const at = Date.now()
          setInfo(next)
          setLoadError(null)
          setReachable(true)
          setNow(at)
          setLoading(false)
          return { info: next, reachable: true, at }
        },
        (e: unknown) => {
          const ok = !unreachable(e)
          const at = Date.now()
          setReachable(ok)
          setLoadError(e)
          setNow(at)
          setLoading(false)
          return { info: null, reachable: ok, at }
        },
      ),
    [],
  )

  useEffect(() => {
    void fetchStatus()
  }, [fetchStatus])

  // Latest values for the polling loop.
  const live = useRef({ baseline, checkPending, reloadPage })
  useEffect(() => {
    live.current = { baseline, checkPending, reloadPage }
  })

  const mode = pollMode({ info, baseline, checkPending: checkPending !== null })
  useEffect(() => {
    if (mode === 'none') return
    let cancelled = false
    const timer = setTimeout(async () => {
      const result = await fetchStatus()
      if (cancelled) return
      const { baseline: base, checkPending: pending } = live.current
      if (base) {
        const next = watchOutcome({ baseline: base, info: result.info, reachable: result.reachable, fetchedAt: result.at, now: Date.now() })
        if (next.kind === 'reload') {
          clearBaseline()
          try {
            sessionStorage.setItem(UPDATED_KEY, next.commit)
          } catch {
            // ignore
          }
          setOutcome({ kind: 'waiting', label: 'Updated. Reloading…' })
          live.current.reloadPage()
          return
        }
        if (next.kind === 'failed' || next.kind === 'gave-up') {
          clearBaseline()
          setBaseline(null)
        }
        setOutcome(next)
      }
      if (pending && result.info) {
        if (checkSettled(pending.marker, result.info)) setCheckPending(null)
        else if (Date.now() - pending.since > CHECK_TIMEOUT_MS) {
          setCheckPending(null)
          setCheckTimedOut(true)
        }
      }
      setTick((n) => n + 1)
    }, UPDATE_POLL_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [mode, tick, fetchStatus])

  const check = async () => {
    setActionError(null)
    setCheckTimedOut(false)
    setOutcome(null)
    const marker = checkMarker(info)
    try {
      await api.updateCheck()
      setCheckPending({ marker, since: Date.now() })
    } catch (e) {
      setActionError(e)
    }
  }

  const sha = info?.status.check?.origin ?? ''
  const start = async () => {
    if (!info || !confirmSha || info.status.check?.origin !== confirmSha || !startGate(info, Date.now()).allowed) return
    setBusy(true)
    setActionError(null)
    try {
      await api.updateStart(confirmSha)
      const next: UpdateBaseline = { runningCommit: info.runningCommit, startedAt: Date.now(), statusUpdatedAt: info.status.updatedAt }
      writeBaseline(next)
      setBaseline(next)
      setOutcome({ kind: 'waiting', label: 'Starting the update…' })
      setConfirming(false)
    } catch (e) {
      setActionError(e)
      setConfirming(false)
    } finally {
      setBusy(false)
    }
  }

  const status = info?.status
  const lastCheck = status?.check ?? null
  const problems = checkProblems(lastCheck)
  const gate = startGate(info, now)
  const latestCommit = lastCheck?.origin ? lastCheck.incoming.find((c) => c.sha === lastCheck.origin) ?? null : null
  const copyInstall = info?.installKind === 'copy'
  const progress =
    outcome?.kind === 'waiting'
      ? outcome.label
      : checkPending || status?.phase === 'checking'
        ? phaseWords('checking')
        : status && mode === 'busy'
          ? phaseWords(status.phase, reachable)
          : null
  const failure =
    outcome?.kind === 'failed' ? outcome.error : status?.phase === 'failed' && status.error ? status.error : null
  const summary = !lastCheck
    ? 'Not checked yet.'
    : !lastCheck.fetchOk
      ? 'The last check could not reach GitHub.'
      : lastCheck.behind > 0
        ? `${lastCheck.behind} update${lastCheck.behind === 1 ? '' : 's'} available.`
        : 'Up to date.'
  const unitsCommand = info?.applyUnitsCommand ?? DEFAULT_APPLY_UNITS_COMMAND
  const autoForHead = info?.unitsApply && info.unitsApply.commit === info.repoHead ? info.unitsApply : null
  const autoState = info ? unitsApplyState(info, autoForHead, now) : null

  return (
    <section className="card stack" aria-labelledby={`${id}-h`} data-testid="update-section">
      <h2 id={`${id}-h`}>Update</h2>
      <ScreenHelp id="update" />
      {updated ? (
        <p className="notice notice-info" role="status">
          Updated: the Pi now runs <code>{shortHash(updated, 7)}</code>.
        </p>
      ) : null}
      {loading && !info ? <Loading /> : null}
      {!info ? <ErrorNotice error={loadError} title="Update status unavailable" /> : null}
      {copyInstall ? (
        <div className="notice notice-warn">
          <p>
            This Pi still runs the copied install, so it cannot update itself. Run bootstrap once (
            <a href={guideHash('update-the-pi')}>Guide → Update the Pi</a>).
          </p>
        </div>
      ) : null}
      {info ? (
        <>
          <dl className="facts">
            <dt>Installed</dt>
            <dd>{info.runningCommit ? <code>{shortHash(info.runningCommit, 7)}</code> : 'Unknown (not a git checkout)'}</dd>
            <dt>Latest</dt>
            <dd>
              {lastCheck?.origin ? (
                <>
                  <code>{shortHash(lastCheck.origin, 7)}</code>
                  {latestCommit ? (
                    <span className="block muted">
                      <Time iso={latestCommit.date} zone={zone} />
                    </span>
                  ) : null}
                </>
              ) : lastCheck ? (
                'Unavailable'
              ) : (
                '—'
              )}
            </dd>
            <dt>Last check</dt>
            <dd>{lastCheck ? <Time iso={lastCheck.checkedAt} zone={zone} /> : 'Never'}</dd>
            <dt>Status</dt>
            <dd>{summary}</dd>
          </dl>

          {info.restartNeeded && !baseline ? (
            <p className="notice notice-warn">
              The code on the Pi (<code>{shortHash(info.repoHead, 7)}</code>) differs from what the UI is running. A restart of the UI
              finishes it (<a href={guideHash('failed-update')}>Guide → Failed update</a>).
            </p>
          ) : null}

          {autoState === 'working' && autoForHead ? (
            <p className="notice notice-info" role="status">
              <strong>Applying {changedWords(info)} automatically…</strong> The Pi installs them by itself (queued{' '}
              <Time iso={autoForHead.at} zone={zone} />
              ); the UI restarts once when it is done.
            </p>
          ) : null}
          {autoState === 'failed' && autoForHead ? (
            <div className="notice notice-warn stack" role="alert">
              <p>
                <strong>The automatic apply failed</strong> (<Time iso={autoForHead.at} zone={zone} />): {autoForHead.error ?? 'no reason recorded'}
              </p>
              {autoForHead.log.length ? (
                <details className="disclosure">
                  <summary>Last lines of the run</summary>
                  <pre>{autoForHead.log.join('\n')}</pre>
                </details>
              ) : null}
              <p>After fixing the cause, run it once by hand:</p>
              <CopyBlock label="Apply units (owner, sudo)" code={unitsCommand} />
            </div>
          ) : null}
          {autoState === 'done' && autoForHead ? (
            <p className="notice notice-info" role="status">
              Unit and package changes were applied automatically (<Time iso={autoForHead.at} zone={zone} />).
            </p>
          ) : null}
          {autoState === 'manual' ? (
            <div className="notice notice-warn stack">
              <p>
                <strong>{info.unitsChanged ? 'Unit files changed' : 'pi-package changed'}</strong>
                {info.unitsChanged && info.piPackageChanged ? ' (and pi-package)' : ''} since they were last installed. After an update the
                Pi applies these by itself once scalar-social-apply-units.path is installed; until then the owner runs this once (
                <a href={guideHash('unit-files-changed')}>Guide → Unit files changed</a>):
              </p>
              <CopyBlock label="Apply units (owner, sudo)" code={unitsCommand} />
            </div>
          ) : null}

          {lastCheck && (lastCheck.changes.units || lastCheck.changes.piPackage) && lastCheck.behind > 0 && !(info.unitsChanged || info.piPackageChanged) ? (
            <div className="notice notice-info stack">
              <p>
                This update changes {lastCheck.changes.units ? 'unit files' : ''}
                {lastCheck.changes.units && lastCheck.changes.piPackage ? ' and ' : ''}
                {lastCheck.changes.piPackage ? 'pi-package' : ''}. The Pi applies them by itself right after the update; this screen shows
                when that is done.
              </p>
            </div>
          ) : null}

          {problems.length ? (
            <div className="notice notice-warn" role="alert">
              <p>
                <strong>Updating is blocked</strong>
              </p>
              <ul className="problem-list">
                {problems.map((p) => (
                  <li key={p.id}>
                    {p.title} <span className="block">Next step: {p.next}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {lastCheck?.fetchOk && lastCheck.incoming.length ? (
            <div className="stack">
              <h3>What’s new</h3>
              {lastCheck.behind > lastCheck.incoming.length ? (
                <p className="hint">
                  Showing the latest {lastCheck.incoming.length} of {lastCheck.behind}.
                </p>
              ) : null}
              <ul className="commit-list">
                {lastCheck.incoming.map((c) => (
                  <li key={c.sha}>
                    <code className="muted">{shortHash(c.sha, 7)}</code> {c.subject}{' '}
                    <span className="muted">
                      · <Time iso={c.date} zone={zone} />
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : null}

      <div role="status" aria-live="polite">
        {progress ? (
          <p className="notice notice-info">
            <StatusBadge tone="info" label={reachable ? 'Working' : 'Restarting'} /> {progress}
          </p>
        ) : null}
        {outcome?.kind === 'gave-up' ? (
          <p className="notice notice-warn">Couldn’t confirm the update. Check the status below before trying again.</p>
        ) : null}
        {checkTimedOut ? <p className="notice notice-warn">The check did not finish within 3 minutes. Try again.</p> : null}
      </div>

      {failure ? (
        <div className="notice notice-error" role="alert">
          <p>
            <strong>Last update failed:</strong> {failure}
          </p>
          <p>
            Nothing was switched; the Pi keeps running <code>{shortHash(info?.runningCommit, 7)}</code>. See{' '}
            <a href={guideHash('failed-update')}>Guide → Failed update</a>.
          </p>
        </div>
      ) : null}
      <ErrorNotice error={actionError} title="Update request failed" />

      {!copyInstall ? (
        <div className="actions">
          {gate.allowed ? (
            <button type="button" className="btn btn-primary" onClick={() => { setConfirmSha(sha); setConfirming(true) }} disabled={busy}>
              Update
            </button>
          ) : null}
          <button type="button" className="btn" onClick={() => void check()} disabled={!info || mode !== 'none'}>
            {checkPending ? 'Checking…' : 'Check for updates'}
          </button>
        </div>
      ) : null}
      {info && !gate.allowed && lastCheck && lastCheck.behind > 0 ? <p className="hint">{gate.reason}</p> : null}

      {status && status.log.length ? (
        <details>
          <summary>Updater log ({status.log.length} lines)</summary>
          <pre className="log-tail">{status.log.join('\n')}</pre>
        </details>
      ) : null}

      {confirming && confirmSha ? (
        <ConfirmDialog
          title="Update the Pi?"
          confirmLabel="Update"
          busy={busy}
          disabled={busy || info?.status.check?.origin !== confirmSha || !startGate(info, now).allowed}
          onConfirm={() => void start()}
          onCancel={() => {
            setConfirming(false)
            setConfirmSha(null)
          }}
        >
          <p>
            The Pi downloads and tests this exact version, waits for any post in progress, switches, and restarts the UI. Publishing state
            is unchanged.
          </p>
          <p>
            Version: <code className="break">{confirmSha}</code>
          </p>
        </ConfirmDialog>
      ) : null}
    </section>
  )
}
