import { useState } from 'react'
import { ApiRequestError, api } from '../../api/client'
import type { StoryHealth, StoryProject, StoryRoute } from '../../api/types'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Loading } from '../../components/Loading'
import { Modal } from '../../components/Modal'
import { ScreenHelp } from '../../components/ScreenHelp'
import { StatusBadge } from '../../components/StatusBadge'
import { Time } from '../../components/Time'
import { useApi } from '../../hooks/useApi'
import { deviceTimeZone } from '../../lib/time'
import { createProblems, jobHash, routeLabel, statusBadge, STEP_LABELS, tierBadge } from '../../lib/storyJobs'

/** Studio › Story jobs: the laptop worker's status, a new recap or series (F2–F6), and every job (F1). */
export function StoryJobsView() {
  const health = useApi(api.storyHealth)
  const projects = useApi(api.storyProjects)
  const settings = useApi(api.storySettings)
  const offline = health.error instanceof ApiRequestError && health.error.status === 503
  return (
    <div className="stack-lg">
      <ScreenHelp id="jobs" />
      <WorkerCard health={health.data} error={health.error} offline={offline} onRetry={() => { health.reload(); projects.reload(); settings.reload() }} />
      <p className="actions">
        <a className="btn" href="#/studio/renders">Renders →</a>
        <a className="btn" href="#/studio/story-settings">Story settings →</a>
      </p>
      {health.data ? (
        <NewJob
          tier={settings.data ? tierBadge(settings.data) : null}
          paidRuns={health.data.paidRunsEnabled}
          onCreated={(p) => { window.location.hash = jobHash(p.id) }}
        />
      ) : null}
      {offline ? null : <ErrorNotice error={projects.error} title="Story jobs unavailable" />}
      {projects.loading && !projects.data && !offline ? <Loading /> : null}
      {projects.data ? <JobList projects={projects.data.projects} onDeleted={projects.reload} /> : null}
    </div>
  )
}

function WorkerCard({ health, error, offline, onRetry }: { health: StoryHealth | null; error: unknown; offline: boolean; onRetry: () => void }) {
  return (
    <section className="card stack" aria-labelledby="story-worker" data-testid="story-worker">
      <h2 id="story-worker">Story worker</h2>
      {offline ? (
        <ErrorNotice error={error} title="Story worker" />
      ) : error ? (
        <ErrorNotice error={error} title="Story worker unavailable" />
      ) : !health ? (
        <Loading />
      ) : (
        <dl className="facts">
          <dt>State</dt>
          <dd>{health.running.length ? `Running ${health.running.join(', ')}` : 'Idle'}</dd>
          <dt>Paid runs</dt>
          <dd>{health.paidRunsEnabled ? 'On: each run needs your OK on its cost estimate' : 'Off on the worker (open engine bugs); free steps only'}</dd>
          <dt>Keys on the laptop</dt>
          <dd>
            {Object.entries(health.keys)
              .map(([k, v]) => `${k} ${v ? 'set' : 'missing'}`)
              .join(' · ')}
          </dd>
          <dt>Version</dt>
          <dd>{health.version}</dd>
        </dl>
      )}
      {error ? (
        <p>
          <button type="button" className="btn" onClick={onRetry}>
            Try again
          </button>
        </p>
      ) : null}
    </section>
  )
}

function NewJob({ tier, paidRuns, onCreated }: { tier: string | null; paidRuns: boolean; onCreated: (p: StoryProject) => void }) {
  const [route, setRoute] = useState<StoryRoute>('recap')
  const [name, setName] = useState('')
  const [brief, setBrief] = useState('')
  const [episodes, setEpisodes] = useState(1)
  const [touched, setTouched] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [askIdea, setAskIdea] = useState(false)
  const problems = createProblems({ route, name, brief, episodes })

  const create = async () => {
    setTouched(true)
    if (problems.length) return
    setBusy(true)
    setError(null)
    try {
      onCreated(await api.storyCreate(route === 'series' ? { route, name: name.trim(), brief: brief.trim(), episodes } : { route, name: name.trim() }))
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const surprise = async () => {
    setAskIdea(false)
    setBusy(true)
    setError(null)
    try {
      const idea = await api.storyRandomIdea()
      setName(idea.name)
      setBrief(idea.brief)
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card stack" aria-labelledby="story-new">
      <h2 id="story-new">New job</h2>
      <fieldset className="stack">
        <legend>Kind</legend>
        <div className="segmented" role="radiogroup" aria-label="Kind">
          {(['recap', 'series'] as const).map((r) => (
            <label key={r} className="choice">
              <input type="radio" name="story-route" value={r} checked={route === r} onChange={() => setRoute(r)} />
              <strong>{routeLabel(r)}</strong>
              <span className="muted">{r === 'recap' ? 'Narrated recap over stock footage, from a movie name or a story idea.' : 'Animated shorts: story, cast, worlds, then video clips per episode.'}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className="field">
        <label htmlFor="story-name">{route === 'recap' ? 'Movie name or story idea' : 'Series name'}</label>
        <input id="story-name" type="text" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
      </div>
      {route === 'series' ? (
        <>
          <div className="field">
            <label htmlFor="story-brief">Brief</label>
            <textarea id="story-brief" rows={4} value={brief} maxLength={2000} onChange={(e) => setBrief(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="story-episodes">Episodes</label>
            <input id="story-episodes" type="number" min={1} max={10} value={episodes} onChange={(e) => setEpisodes(Number(e.target.value))} />
          </div>
          {tier ? (
            <p className="muted">
              Video quality: <StatusBadge tone="info" label={tier} /> <a href="#/studio/story-settings">Change in Story settings</a>
            </p>
          ) : null}
        </>
      ) : null}
      {touched && problems.length ? (
        <ul className="field-issues">
          {problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      ) : null}
      <ErrorNotice error={error} title="Could not create the job" />
      <div className="actions">
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void create()}>
          Create job
        </button>
        {route === 'series' ? (
          <button type="button" className="btn" disabled={busy || !paidRuns} onClick={() => setAskIdea(true)} title={paidRuns ? undefined : 'Paid calls are off on the worker'}>
            Surprise me
          </button>
        ) : null}
      </div>
      <p className="hint">Creating a job costs nothing. Running it shows the cost estimate first.</p>
      {askIdea ? (
        <Modal title="Ask Gemini for a series idea?" onClose={() => setAskIdea(false)}>
          <div className="stack">
            <p>One short Gemini text request on the laptop worker. It is not priced in advance (typically well under a cent).</p>
            <div className="actions">
              <button type="button" className="btn btn-primary" data-autofocus onClick={() => void surprise()}>
                Ask Gemini
              </button>
              <button type="button" className="btn btn-quiet" onClick={() => setAskIdea(false)}>
                Cancel
              </button>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  )
}

function JobList({ projects, onDeleted }: { projects: StoryProject[]; onDeleted: () => void }) {
  const [deleting, setDeleting] = useState<StoryProject | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const sorted = [...projects].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
  const remove = async (p: StoryProject) => {
    setBusy(true)
    setError(null)
    try {
      await api.storyDelete(p.id, p.id)
      setDeleting(null)
      onDeleted()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="card stack" aria-labelledby="story-jobs">
      <h2 id="story-jobs">Jobs</h2>
      {sorted.length === 0 ? <p className="muted">No story jobs yet.</p> : null}
      <ul className="row-list">
        {sorted.map((p) => {
          const badge = statusBadge(p.status, p.running)
          return (
            <li key={p.id} className="stack" data-testid="story-job">
              <p className="row-head">
                <a href={jobHash(p.id)}>
                  <strong>{p.name}</strong>
                </a>{' '}
                <StatusBadge tone={badge.tone} label={badge.label} className={p.running ? 'badge-pulse' : ''} />
              </p>
              <p className="muted">
                {routeLabel(p.route)}
                {p.route === 'series' ? ` · ${p.params.num_episodes ?? 1} episode${(p.params.num_episodes ?? 1) === 1 ? '' : 's'}` : ''}
                {p.currentStep && p.status !== 'completed' ? ` · step ${STEP_LABELS[p.currentStep as keyof typeof STEP_LABELS] ?? p.currentStep}` : ''} · created <Time iso={p.createdAt} zone={deviceTimeZone()} />
              </p>
              {p.params.brief ? <p className="clamp">{p.params.brief}</p> : null}
              <div className="actions">
                <a className="btn" href={jobHash(p.id)}>
                  Open
                </a>
                <button type="button" className="btn btn-quiet" disabled={p.running} onClick={() => setDeleting(p)}>
                  Delete
                </button>
              </div>
            </li>
          )
        })}
      </ul>
      {deleting ? (
        <Modal title={`Delete ${deleting.name}?`} onClose={() => setDeleting(null)}>
          <div className="stack">
            <p>This deletes the job and every file it made on the laptop (scripts, images, clips, videos). It cannot be undone.</p>
            <ErrorNotice error={error} title="Could not delete" />
            <div className="actions">
              <button type="button" className="btn btn-danger" disabled={busy} onClick={() => void remove(deleting)}>
                Delete {deleting.name}
              </button>
              <button type="button" className="btn btn-quiet" data-autofocus onClick={() => setDeleting(null)}>
                Keep it
              </button>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  )
}
