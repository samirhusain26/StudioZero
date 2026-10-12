import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import type { Catalog } from '../../api/types'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Loading } from '../../components/Loading'
import { ScreenHelp } from '../../components/ScreenHelp'
import { useApi } from '../../hooks/useApi'
import { engineOf, projectOf, projectsInOrder } from '../../lib/catalog'
import {
  AUDIO_MOODS,
  BEATS,
  buildNewFormatPrompt,
  CONSTRAINTS_LIMIT,
  MAX_SECONDS,
  MIN_SECONDS,
  newPlanProblems,
  readDraft,
  slugOf,
  TOPIC_LIMIT,
  VOCABULARY,
  writeDraft,
  type NewFormatPlan,
  type NewKind,
} from '../../lib/promptNewFormat'

/** Studio › New format, style or project (prompt builder mode 2). */
export function NewFormatView() {
  const catalog = useApi(api.catalog)
  return (
    <div className="stack-lg">
      <p>
        <a href="#/studio">← Studio</a>
      </p>
      <ScreenHelp id="newFormat" />
      <ErrorNotice error={catalog.error} title="Studio catalog unavailable" />
      {catalog.loading && !catalog.data ? <Loading /> : null}
      {catalog.data ? <NewFormatForm catalog={catalog.data} /> : null}
    </div>
  )
}

const KINDS: { id: NewKind; label: string; hint: string }[] = [
  { id: 'format', label: 'New format', hint: 'A new kind of episode for an existing project.' },
  { id: 'style', label: 'New style', hint: 'A new look for an existing game’s formats (motion engine).' },
  { id: 'project', label: 'New project', hint: 'A new project with its first format.' },
]

export function NewFormatForm({ catalog, now }: { catalog: Catalog; now?: Date }) {
  const [plan, setPlan] = useState<NewFormatPlan>(() => readDraft(catalog))
  const [status, setStatus] = useState('')
  const [touched, setTouched] = useState(false)
  useEffect(() => {
    writeDraft(plan)
  }, [plan])
  const set = (patch: Partial<NewFormatPlan>) => {
    setStatus('')
    setPlan((p) => ({ ...p, ...patch }))
  }
  const problems = newPlanProblems(catalog, plan)
  const prompt = useMemo(() => (problems.length ? '' : buildNewFormatPrompt(catalog, plan, now)), [catalog, plan, now, problems.length])
  const project = plan.kind === 'project' ? null : projectOf(catalog, plan.project)
  const engine = engineOf(catalog, plan.engine)
  const baseFormats = project?.formats.filter((f) => f.engine === plan.engine) ?? []
  const games = project?.games ?? []
  const copy = async () => {
    setTouched(true)
    if (!prompt) return
    try {
      await navigator.clipboard.writeText(prompt)
      setStatus('Copied. Paste it into Claude Code in the StudioZero folder on the Mac.')
    } catch {
      setStatus('Copy failed; select the prompt below and copy it manually.')
    }
  }
  const toggle = (list: string[], item: string, order: readonly string[]) =>
    list.includes(item) ? list.filter((x) => x !== item) : order.filter((x) => x === item || list.includes(x))

  return (
    <>
      <section className="card stack" aria-labelledby="new-what">
        <h2 id="new-what">What to make</h2>
        <div className="segmented" role="radiogroup" aria-label="Kind">
          {KINDS.map((k) => (
            <label key={k.id} className="choice">
              <input
                type="radio"
                name="new-kind"
                checked={plan.kind === k.id}
                onChange={() => set({ kind: k.id, ...(k.id === 'style' ? { engine: 'motion', route: '' } : {}) })}
              />
              <strong>{k.label}</strong>
              <span className="muted">{k.hint}</span>
            </label>
          ))}
        </div>
        {plan.kind === 'project' ? (
          <div className="field">
            <label htmlFor="new-project-name">Project name</label>
            <input id="new-project-name" type="text" maxLength={60} value={plan.projectName} onChange={(e) => set({ projectName: e.target.value })} />
            {plan.projectName.trim() ? <span className="muted">id {slugOf(plan.projectName)}</span> : null}
          </div>
        ) : (
          <div className="field">
            <label htmlFor="new-project">Project</label>
            <select id="new-project" value={plan.project} onChange={(e) => set({ project: e.target.value, game: '', baseFormat: '' })}>
              {projectsInOrder(catalog).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="field">
          <label htmlFor="new-engine">Engine</label>
          <select id="new-engine" value={plan.engine} disabled={plan.kind === 'style'} onChange={(e) => set({ engine: e.target.value, route: '', baseFormat: '' })}>
            {catalog.engines.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
          {engine ? <span className="muted">{engine.summary}</span> : null}
        </div>
        {engine?.routes.length ? (
          <div className="field">
            <label htmlFor="new-route">Route</label>
            <select id="new-route" value={plan.route} onChange={(e) => set({ route: e.target.value })}>
              <option value="">Choose…</option>
              {engine.routes.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </div>
        ) : null}
        {games.length && engine?.id === 'motion' ? (
          <div className="field">
            <label htmlFor="new-game">Game</label>
            <select id="new-game" value={plan.game} onChange={(e) => set({ game: e.target.value })}>
              <option value="">{plan.kind === 'style' ? 'Choose…' : 'None'}</option>
              {games.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          </div>
        ) : null}
        <div className="field">
          <label htmlFor="new-name">{plan.kind === 'style' ? 'Style name' : plan.kind === 'project' ? 'First format name' : 'Format name'}</label>
          <input id="new-name" type="text" maxLength={60} value={plan.name} onChange={(e) => set({ name: e.target.value })} />
          {plan.name.trim() ? <span className="muted">id {slugOf(plan.name)}</span> : null}
        </div>
        {baseFormats.length ? (
          <div className="field">
            <label htmlFor="new-base">Start from</label>
            <select id="new-base" value={plan.baseFormat} onChange={(e) => set({ baseFormat: e.target.value })}>
              <option value="">From scratch</option>
              {baseFormats.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                </option>
              ))}
            </select>
          </div>
        ) : null}
        <div className="field">
          <label htmlFor="new-topic">Topic</label>
          <textarea id="new-topic" rows={3} maxLength={TOPIC_LIMIT} value={plan.topic} onChange={(e) => set({ topic: e.target.value })} />
        </div>
      </section>

      <section className="card stack" aria-labelledby="new-how">
        <h2 id="new-how">How it looks and sounds</h2>
        <fieldset className="stack">
          <legend>Visual vocabulary</legend>
          {VOCABULARY.map((v) => (
            <div key={v} className="field-check">
              <input id={`new-v-${slugOf(v)}`} type="checkbox" checked={plan.vocabulary.includes(v)} onChange={() => set({ vocabulary: toggle(plan.vocabulary, v, VOCABULARY) })} />
              <label htmlFor={`new-v-${slugOf(v)}`}>{v}</label>
            </div>
          ))}
        </fieldset>
        <fieldset className="stack">
          <legend>Structure (in this order)</legend>
          {BEATS.map((b) => (
            <div key={b} className="field-check">
              <input id={`new-b-${slugOf(b)}`} type="checkbox" checked={plan.beats.includes(b)} onChange={() => set({ beats: toggle(plan.beats, b, BEATS) })} />
              <label htmlFor={`new-b-${slugOf(b)}`}>{b}</label>
            </div>
          ))}
        </fieldset>
        <div className="field">
          <label htmlFor="new-length">Length (seconds)</label>
          <input id="new-length" type="number" min={MIN_SECONDS} max={MAX_SECONDS} value={plan.lengthSeconds} onChange={(e) => set({ lengthSeconds: Number(e.target.value) })} />
        </div>
        <div className="field">
          <label htmlFor="new-mood">Audio mood</label>
          <select id="new-mood" value={plan.audioMood} onChange={(e) => set({ audioMood: e.target.value })}>
            {AUDIO_MOODS.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="new-constraints">Constraints (one per line)</label>
          <textarea id="new-constraints" rows={4} maxLength={CONSTRAINTS_LIMIT} value={plan.constraints} onChange={(e) => set({ constraints: e.target.value })} />
        </div>
      </section>

      <section className="card stack" aria-labelledby="new-prompt">
        <h2 id="new-prompt">Prompt for Claude</h2>
        <p>Claude builds it on the Mac, makes one pilot, puts it where you can watch it (Studio › Export’s Player, or Story renders) and stops for your review.</p>
        {touched && problems.length ? (
          <ul className="field-issues">
            {problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        ) : null}
        <div className="actions">
          <button type="button" className="btn btn-primary" disabled={touched && problems.length > 0} onClick={() => void copy()}>
            Copy prompt for Claude
          </button>
          <span role="status" aria-live="polite" className="muted">
            {status}
          </span>
        </div>
        {prompt ? (
          <details>
            <summary>Show the prompt</summary>
            <pre className="log-tail" data-testid="new-format-prompt">
              {prompt}
            </pre>
          </details>
        ) : null}
        <p className="hint">The draft stays in this browser.</p>
      </section>
    </>
  )
}
