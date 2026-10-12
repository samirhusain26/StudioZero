import { useEffect, useRef, useState } from 'react'
import { api, storyFileUrl } from '../../api/client'
import type { StoryArtifact, StoryEstimate, StoryEvent, StoryProjectDetail, StorySettings } from '../../api/types'
import { Chip } from '../../components/Chip'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Loading } from '../../components/Loading'
import { Modal } from '../../components/Modal'
import { ScreenHelp } from '../../components/ScreenHelp'
import { StatusBadge } from '../../components/StatusBadge'
import { useApi } from '../../hooks/useApi'
import { formatBytes } from '../../lib/format'
import {
  budgetView,
  elapsedText,
  eventText,
  filterEvents,
  lastUpdateText,
  mergeEvents,
  parseScript,
  pollingNote,
  pollMs,
  projectInfo,
  routeLabel,
  runAction,
  statusBadge,
  stepRail,
  tierBadge,
  usd,
  wordCount,
  type LogFilter,
  type RailStep,
} from '../../lib/storyJobs'

/** Polls the job (fast while it runs) and appends its new log lines. A worker restart starts the log again. */
function useStoryJob(id: string) {
  const [detail, setDetail] = useState<StoryProjectDetail | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [events, setEvents] = useState<StoryEvent[]>([])
  const [nonce, setNonce] = useState(0)
  const seq = useRef(0)
  useEffect(() => {
    let stopped = false
    let timer: number | undefined
    const tick = async () => {
      let running = false
      try {
        const d = await api.storyProject(id)
        if (stopped) return
        setDetail(d)
        running = d.running
        const e = await api.storyEvents(id, seq.current)
        if (stopped) return
        if (e.last < seq.current) {
          seq.current = 0
          setEvents([])
        } else {
          seq.current = e.last
          setEvents((prev) => mergeEvents(prev, e.events))
        }
        running = running || e.running
        setError(null)
      } catch (err) {
        if (!stopped) setError(err)
      }
      if (!stopped) timer = window.setTimeout(() => void tick(), pollMs(running))
    }
    void tick()
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [id, nonce])
  return { detail, error, events, setDetail, refresh: () => setNonce((n) => n + 1) }
}

/** Studio › Story job: run with a confirmed estimate, follow it, review and decide (parity F7–F18). */
export function StoryJobView({ id }: { id: string }) {
  const { detail, error, events, setDetail, refresh } = useStoryJob(id)
  const settings = useApi(api.storySettings)
  const [estimate, setEstimate] = useState<StoryEstimate | null>(null)
  const [actionError, setActionError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [artifacts, setArtifacts] = useState<RailStep | null>(null)

  if (!detail) {
    return (
      <div className="stack-lg">
        <p>
          <a href="#/studio/jobs">← Story jobs</a>
        </p>
        <ErrorNotice error={error} title="Story job unavailable" />
        {error ? null : <Loading />}
      </div>
    )
  }

  const act = async (work: () => Promise<void>) => {
    setBusy(true)
    setActionError(null)
    try {
      await work()
    } catch (e) {
      setActionError(e)
    } finally {
      setBusy(false)
    }
  }
  const openEstimate = () => act(async () => setEstimate(await api.storyEstimate(id)))
  const cancel = () =>
    act(async () => {
      await api.storyCancel(id)
      refresh()
    })

  const badge = statusBadge(detail.status, detail.running)
  const action = runAction(detail)
  const polling = pollingNote(events, detail.running)
  return (
    <div className="stack-lg">
      <p>
        <a href="#/studio/jobs">← Story jobs</a>
      </p>
      <ScreenHelp id="job" />
      <section className="card stack" aria-labelledby="story-job-head" data-testid="story-job-head">
        <h2 id="story-job-head">
          {detail.name} <StatusBadge tone={badge.tone} label={badge.label} className={detail.running ? 'badge-pulse' : ''} />
        </h2>
        <p className="muted">
          {routeLabel(detail.route)}
          {detail.route === 'series' && settings.data ? (
            <>
              {' · '}
              <StatusBadge tone="info" label={tierBadge(settings.data, detail.videoModel)} />
            </>
          ) : null}
        </p>
        {detail.params.brief ? <p>{detail.params.brief}</p> : null}
        {polling ? (
          <p className="notice notice-info" role="status" data-testid="story-polling">
            {polling}
          </p>
        ) : null}
        <ErrorNotice error={error} title="Lost touch with the worker" />
        {detail.status === 'error' && detail.error ? (
          <div className="notice notice-error" role="alert">
            <p className="notice-title">
              <strong>The run stopped:</strong> {detail.error}
            </p>
          </div>
        ) : null}
        <ErrorNotice error={actionError} title="Could not do that" />
        <div className="actions">
          {action.kind === 'run' ? (
            <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void openEstimate()}>
              {action.label}…
            </button>
          ) : (
            <span className="muted">{action.reason}</span>
          )}
          {detail.running ? (
            <button type="button" className="btn" disabled={busy} onClick={() => void cancel()}>
              Cancel run
            </button>
          ) : null}
        </div>
      </section>

      {detail.route === 'recap' && detail.script && !detail.running && !detail.scriptApproved && ['review', 'paused', 'error'].includes(detail.status) ? (
        <ScriptReview key={detail.updatedAt} detail={detail} onSaved={(p) => setDetail({ ...detail, ...p })} />
      ) : null}

      {detail.failedScene && detail.status === 'scene_failed' ? (
        <SceneFailed
          detail={detail}
          settings={settings.data}
          onDecided={(next) => {
            setDetail({ ...detail, ...next })
            setEstimate(next.estimate)
          }}
        />
      ) : null}

      <div className="grid-2">
        <InfoPanel detail={detail} />
        <BudgetPanel detail={detail} />
      </div>

      {detail.route === 'series' ? <StepRail detail={detail} onOpen={setArtifacts} /> : null}

      <JobLog events={events} running={detail.running} />

      {estimate ? (
        <RunDialog
          id={id}
          estimate={estimate}
          onClose={() => setEstimate(null)}
          onStarted={() => {
            setEstimate(null)
            refresh()
          }}
          onRefresh={(e) => setEstimate(e)}
        />
      ) : null}
      {artifacts ? <ArtifactDialog id={id} step={artifacts} onClose={() => setArtifacts(null)} /> : null}
    </div>
  )
}

/** F7: the estimate the worker signed; confirming sends it back unchanged, and the worker checks it and the budget again. */
function RunDialog({
  id,
  estimate,
  onClose,
  onStarted,
  onRefresh,
}: {
  id: string
  estimate: StoryEstimate
  onClose: () => void
  onStarted: () => void
  onRefresh: (e: StoryEstimate) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const over = estimate.spentUsd + estimate.estimateUsd > estimate.maxBudgetUsd + 1e-9
  const run = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.storyRun(id, { token: estimate.token, estimateUsd: estimate.estimateUsd })
      onStarted()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }
  const again = async () => {
    setBusy(true)
    setError(null)
    try {
      onRefresh(await api.storyEstimate(id))
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }
  return (
    <Modal title="Cost estimate" onClose={onClose}>
      <div className="stack" data-testid="story-estimate">
        {estimate.lines.length ? (
          <ul className="plain-list">
            {estimate.lines.map((l) => (
              <li key={l.what}>
                {l.what}: <strong>{usd(l.usd)}</strong>
              </li>
            ))}
          </ul>
        ) : null}
        <p>
          Estimated: <strong>{usd(estimate.estimateUsd)}</strong>
          {estimate.unpriced.length ? ' plus calls the worker cannot price in advance:' : ''}
        </p>
        {estimate.unpriced.length ? (
          <ul className="plain-list muted">
            {estimate.unpriced.map((u) => (
              <li key={u}>{u}</li>
            ))}
          </ul>
        ) : null}
        <p>
          Spent so far {usd(estimate.spentUsd)} of this job&apos;s {usd(estimate.maxBudgetUsd)} budget.
          {estimate.originalsBudget.monthlyUsd
            ? ` Originals budget: $${estimate.originalsBudget.monthlyUsd} a month.`
            : ' The Originals monthly budget is not set yet (your decision).'}
        </p>
        {over ? <p className="notice notice-warn">This run would go over the job&apos;s budget; the worker will refuse it. Raise the budget in Story settings or choose a cheaper model.</p> : null}
        {!estimate.paidRunsEnabled ? <p className="notice notice-warn">Paid runs are switched off on the worker until the open engine bugs are fixed.</p> : null}
        <ErrorNotice error={error} title="Not started" />
        <div className="actions">
          <button type="button" className="btn btn-primary" disabled={busy || over || !estimate.paidRunsEnabled} onClick={() => void run()}>
            {estimate.unpriced.length ? `Run: ${usd(estimate.estimateUsd)} + unpriced calls` : `Run for about ${usd(estimate.estimateUsd)}`}
          </button>
          <button type="button" className="btn" disabled={busy} onClick={() => void again()}>
            Refresh estimate
          </button>
          <button type="button" className="btn btn-quiet" data-autofocus onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </Modal>
  )
}

/** F14: the recap script waits here; edits are saved and approved, and the next run narrates exactly that (B1). */
function ScriptReview({ detail, onSaved }: { detail: StoryProjectDetail; onSaved: (p: Partial<StoryProjectDetail>) => void }) {
  const original = JSON.stringify(detail.script, null, 2)
  const [text, setText] = useState(original)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const parsed = parseScript(text)
  const approve = async () => {
    if ('error' in parsed) return
    setBusy(true)
    setError(null)
    try {
      if (text !== original) onSaved(await api.storySaveScript(detail.id, parsed.script))
      onSaved(await api.storyApproveScript(detail.id))
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="card stack" aria-labelledby="story-script">
      <h2 id="story-script">Review the script</h2>
      <p>Edit the JSON if you need to, then approve it. Continue then narrates and renders exactly this script.</p>
      <div className="field">
        <label htmlFor="story-script-text">Script (JSON)</label>
        <textarea id="story-script-text" rows={18} spellCheck={false} value={text} onChange={(e) => setText(e.target.value)} />
      </div>
      {'error' in parsed ? <p className="field-issues">{parsed.error}</p> : null}
      <ErrorNotice error={error} title="Script not saved" />
      <div className="actions">
        <button type="button" className="btn btn-primary" disabled={busy || 'error' in parsed} onClick={() => void approve()}>
          {text !== original ? 'Save and approve' : 'Approve script'}
        </button>
        {text !== original ? (
          <button type="button" className="btn btn-quiet" onClick={() => setText(original)}>
            Undo edits
          </button>
        ) : null}
      </div>
    </section>
  )
}

/** F15: a series scene failed; the decision is saved, then the next run needs a new confirmed estimate. */
function SceneFailed({
  detail,
  settings,
  onDecided,
}: {
  detail: StoryProjectDetail
  settings: StorySettings | null
  onDecided: (p: Awaited<ReturnType<typeof api.storyScene>>) => void
}) {
  const failed = detail.failedScene
  const [prompt, setPrompt] = useState(failed?.prompt ?? '')
  const [model, setModel] = useState(detail.videoModel)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  if (!failed) return null
  const decide = async (action: 'retry' | 'edit' | 'skip' | 'change_model') => {
    setBusy(true)
    setError(null)
    try {
      onDecided(await api.storyScene(detail.id, action, action === 'edit' ? prompt : '', action === 'change_model' ? model : ''))
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }
  const models = settings ? Object.values(settings.tiers).flat() : []
  return (
    <section className="card stack" aria-labelledby="story-scene">
      <h2 id="story-scene">
        Scene {failed.scene ?? '?'} of episode {failed.episode ?? '?'} failed
      </h2>
      {failed.error ? <pre className="log-tail">{failed.error}</pre> : null}
      <div className="field">
        <label htmlFor="story-scene-prompt">Prompt</label>
        <textarea id="story-scene-prompt" rows={6} value={prompt} onChange={(e) => setPrompt(e.target.value)} />
        <span className="muted">{wordCount(prompt)} words</span>
      </div>
      {models.length ? (
        <div className="field">
          <label htmlFor="story-scene-model">Video model for this job</label>
          <select id="story-scene-model" value={model} onChange={(e) => setModel(e.target.value)}>
            {models.map((m) =>
              m ? (
                <option key={m.id} value={m.id}>
                  {m.name} · ${m.costPerSecondUsd}/s
                </option>
              ) : null,
            )}
          </select>
        </div>
      ) : null}
      <ErrorNotice error={error} title="Decision not saved" />
      <div className="actions">
        <button type="button" className="btn" disabled={busy} onClick={() => void decide('retry')}>
          Retry
        </button>
        <button type="button" className="btn" disabled={busy || !prompt.trim() || prompt === failed.prompt} onClick={() => void decide('edit')}>
          Save edits &amp; retry
        </button>
        <button type="button" className="btn" disabled={busy || model === detail.videoModel} onClick={() => void decide('change_model')}>
          Change model &amp; retry
        </button>
        <button type="button" className="btn btn-quiet" disabled={busy} onClick={() => void decide('skip')}>
          Skip scene
        </button>
      </div>
      <p className="hint">Each choice shows a new cost estimate before anything runs.</p>
    </section>
  )
}

/** F11. */
function InfoPanel({ detail }: { detail: StoryProjectDetail }) {
  const info = projectInfo(detail)
  return (
    <section className="card stack" aria-labelledby="story-info">
      <h2 id="story-info">Job</h2>
      <dl className="facts">
        <dt>Kind</dt>
        <dd>{routeLabel(detail.route)}</dd>
        {detail.route === 'series' ? (
          <>
            <dt>Episodes</dt>
            <dd>{detail.params.num_episodes ?? 1}</dd>
            <dt>Steps</dt>
            <dd>
              {info.stepsDone} of {info.stepsTotal}
              {info.totalSeconds ? ` · ${elapsedText(info.totalSeconds)} of work` : ''}
            </dd>
            <dt>Made</dt>
            <dd>
              {info.clips} clip{info.clips === 1 ? '' : 's'} · {info.files} file{info.files === 1 ? '' : 's'}
            </dd>
          </>
        ) : (
          <>
            <dt>Script</dt>
            <dd>{detail.scriptApproved ? 'Approved' : detail.script ? 'Waiting for review' : 'Not written yet'}</dd>
          </>
        )}
        <dt>Created</dt>
        <dd>{new Date(detail.createdAt).toLocaleString()}</dd>
        <dt>Updated</dt>
        <dd>{new Date(detail.updatedAt).toLocaleString()}</dd>
      </dl>
    </section>
  )
}

/** F12: from the job's spend ledger on the laptop. */
function BudgetPanel({ detail }: { detail: StoryProjectDetail }) {
  const b = budgetView(detail.spentUsd, detail.maxBudgetUsd)
  return (
    <section className="card stack" aria-labelledby="story-budget">
      <h2 id="story-budget">Budget</h2>
      <progress max={100} value={b.percent} aria-label={`${b.percent}% of the budget used`} />
      <p>
        {usd(b.spentUsd)} of {usd(b.maxUsd)} spent ({b.percent}%) · {usd(b.remainingUsd)} left
      </p>
      {b.over ? <p className="notice notice-warn">Over budget: the worker refuses further paid runs for this job.</p> : null}
      <p className="muted">Video clips are counted as they are billed; text, image and voice calls are not priced yet.</p>
    </section>
  )
}

const PHASE: Record<RailStep['phase'], { label: string; tone: 'good' | 'bad' | 'info' | 'neutral' }> = {
  done: { label: 'Done', tone: 'good' },
  error: { label: 'Error', tone: 'bad' },
  running: { label: 'Running', tone: 'info' },
  pending: { label: 'Pending', tone: 'neutral' },
}

/** F9: pre-production, then each episode (set designer included: B7). Finished steps open their files (F10). */
function StepRail({ detail, onOpen }: { detail: StoryProjectDetail; onOpen: (s: RailStep) => void }) {
  const rail = stepRail(detail.pipelineState, detail.params.num_episodes ?? 1, detail.running)
  const row = (s: RailStep) => (
    <li key={`${s.episode ?? 0}-${s.name}`} className="stack" data-testid="story-step">
      <p className="row-head">
        {s.phase === 'done' && s.artifacts > 0 ? (
          <button type="button" className="link-button" onClick={() => onOpen(s)}>
            {s.label}
          </button>
        ) : (
          <strong>{s.label}</strong>
        )}{' '}
        <StatusBadge tone={PHASE[s.phase].tone} label={PHASE[s.phase].label} />
        {s.seconds !== null ? <span className="muted"> {elapsedText(s.seconds)}</span> : null}
        {s.artifacts ? <span className="muted"> · {s.artifacts} file{s.artifacts === 1 ? '' : 's'}</span> : null}
      </p>
      {s.error ? <p className="field-issues">{s.error}</p> : null}
    </li>
  )
  return (
    <section className="card stack" aria-labelledby="story-steps">
      <h2 id="story-steps">Steps</h2>
      <h3>Pre-production</h3>
      <ul className="row-list">{rail.preProduction.map(row)}</ul>
      {rail.episodes.map((e) => (
        <div key={e.episode} className="stack">
          <h3>
            Episode {e.episode} <StatusBadge tone={PHASE[e.phase].tone} label={PHASE[e.phase].label} />
          </h3>
          <ul className="row-list">{e.steps.map(row)}</ul>
        </div>
      ))}
    </section>
  )
}

/** F10: a step's files: images, clips and pretty JSON. */
function ArtifactDialog({ id, step, onClose }: { id: string; step: RailStep; onClose: () => void }) {
  const files = useApi(() => api.storyArtifacts(id, step.name, step.episode ?? undefined), `${id}/${step.name}/${step.episode ?? ''}`)
  return (
    <Modal title={`${step.label}${step.episode ? ` · episode ${step.episode}` : ''}`} onClose={onClose} variant="drawer">
      <div className="stack">
        <ErrorNotice error={files.error} title="Files unavailable" />
        {files.loading && !files.data ? <Loading /> : null}
        {files.data?.files.length === 0 ? <p className="muted">No files are left for this step on the laptop.</p> : null}
        {files.data ? (
          <ul className="row-list">
            {files.data.files.map((f) => (
              <ArtifactItem key={f.path} id={id} file={f} />
            ))}
          </ul>
        ) : null}
      </div>
    </Modal>
  )
}

function ArtifactItem({ id, file }: { id: string; file: StoryArtifact }) {
  const url = storyFileUrl(id, file.path)
  return (
    <li className="stack">
      <p className="row-head">
        <code>{file.path}</code> <span className="muted">{formatBytes(file.bytes)}</span>
      </p>
      {file.kind === 'image' ? <img className="story-image" src={url} alt={file.path} loading="lazy" /> : null}
      {file.kind === 'video' ? <video className="player" src={url} controls preload="metadata" playsInline /> : null}
      {file.kind === 'json' && file.json !== null ? <JsonView value={file.json} depth={0} /> : null}
      {file.kind === 'text' || file.kind === 'file' || (file.kind === 'json' && file.json === null) ? (
        <a href={url} target="_blank" rel="noopener noreferrer">
          Open
        </a>
      ) : null}
    </li>
  )
}

const LABEL = (key: string) => key.replace(/_/g, ' ')

/** Readable JSON: objects as fact lists, arrays as numbered lists, long text wrapped. */
export function JsonView({ value, depth }: { value: unknown; depth: number }) {
  if (value === null || value === undefined) return <span className="muted">—</span>
  if (typeof value !== 'object') return <span className="story-text">{String(value)}</span>
  if (depth > 5) return <code className="story-text">{JSON.stringify(value)}</code>
  if (Array.isArray(value)) {
    if (value.every((v) => typeof v !== 'object' || v === null)) return <span className="story-text">{value.map(String).join(', ')}</span>
    return (
      <ol className="steps">
        {value.map((v, i) => (
          <li key={i}>
            <JsonView value={v} depth={depth + 1} />
          </li>
        ))}
      </ol>
    )
  }
  return (
    <dl className="facts">
      {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
        <div key={k} className="contents">
          <dt>{LABEL(k)}</dt>
          <dd>
            <JsonView value={v} depth={depth + 1} />
          </dd>
        </div>
      ))}
    </dl>
  )
}

/** F8: the run log with filters, auto-scroll and the time since the last line. */
function JobLog({ events, running }: { events: StoryEvent[]; running: boolean }) {
  const [filter, setFilter] = useState<LogFilter>('all')
  const [follow, setFollow] = useState(true)
  const [now, setNow] = useState(() => Date.now())
  const box = useRef<HTMLPreElement>(null)
  const shown = filterEvents(events, filter)
  useEffect(() => {
    if (!running) return
    const t = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(t)
  }, [running])
  useEffect(() => {
    if (follow && box.current) box.current.scrollTop = box.current.scrollHeight
  }, [shown.length, follow])
  const last = lastUpdateText(events, now)
  return (
    <section className="card stack" aria-labelledby="story-log">
      <h2 id="story-log">Log</h2>
      <div className="chip-row" role="group" aria-label="Show">
        {(['all', 'steps', 'errors'] as const).map((f) => (
          <Chip key={f} pressed={filter === f} onClick={() => setFilter(f)}>
            {f === 'all' ? 'All' : f === 'steps' ? 'Steps' : 'Errors'}
          </Chip>
        ))}
      </div>
      <div className="field-check">
        <input id="story-follow" type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} />
        <label htmlFor="story-follow">Follow new lines</label>
      </div>
      {running && last ? <p className="muted">{last}</p> : null}
      {shown.length === 0 ? (
        <p className="muted">No log lines since the worker started.</p>
      ) : (
        <pre ref={box} className="log-tail" data-testid="story-log-lines">
          {shown.map((e) => `${e.at.slice(11, 19)}  ${e.kind === 'error' ? '✕ ' : ''}${eventText(e)}`).join('\n')}
        </pre>
      )}
    </section>
  )
}

