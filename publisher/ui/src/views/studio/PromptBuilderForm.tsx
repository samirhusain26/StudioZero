import { useId, useState } from 'react'
import type { Catalog } from '../../api/types'
import { bedsFor, formatOf, projectOf, stylesFor } from '../../lib/catalog'
import {
  applyPreset,
  CALM,
  deletePreset,
  evenMix,
  MAX_PER_FORMAT,
  MAX_SPARES,
  plannedGames,
  readPresets,
  savePreset,
  totalEpisodes,
  type BatchPlan,
  type DifficultyMix,
  type PlanPreset,
} from '../../lib/promptBuilder'

function toCount(value: string, max: number): number {
  const n = Number(value)
  return Number.isInteger(n) ? Math.min(Math.max(n, 0), max) : 0
}

/**
 * Prompt builder mode 1 (Studio › Make a batch): every choice comes from the catalog; presets stay in this browser.
 * The parent owns the plan and turns it into the brief and the prompt.
 */
export function PromptBuilderForm({ catalog, plan, onChange }: { catalog: Catalog; plan: BatchPlan; onChange: (plan: BatchPlan) => void }) {
  const id = useId()
  const project = projectOf(catalog, plan.project)
  const games = Boolean(project?.games?.length)
  const [presets, setPresets] = useState<PlanPreset[]>(() => readPresets().filter((p) => p.plan.project === plan.project))
  const [presetName, setPresetName] = useState('')
  const [chosen, setChosen] = useState('')
  const [presetStatus, setPresetStatus] = useState('')
  if (!project) return null

  const set = (patch: Partial<BatchPlan>) => onChange({ ...plan, ...patch })
  const setRow = (format: string, count: number, mix?: DifficultyMix) =>
    set({ scope: plan.scope.map((r) => (r.format === format ? { format, count, mix: mix ?? evenMix(count) } : r)) })
  const refresh = () => setPresets(readPresets().filter((p) => p.plan.project === plan.project))

  const apply = () => {
    const preset = presets.find((p) => p.name === chosen)
    const next = preset ? applyPreset(catalog, preset, plan.batchId) : null
    if (next) {
      onChange(next)
      setPresetStatus(`Applied “${preset?.name}”. Options the catalog no longer has were left out.`)
    }
  }
  const save = () => {
    const ok = savePreset(presetName, plan)
    refresh()
    setPresetStatus(ok ? `Saved “${presetName.trim()}” in this browser.` : 'Could not save: give it a name, or this browser blocks storage.')
    if (ok) setChosen(presetName.trim())
  }
  const remove = () => {
    if (!chosen) return
    deletePreset(chosen)
    refresh()
    setPresetStatus(`Deleted “${chosen}”.`)
    setChosen('')
  }

  return (
    <div className="stack" data-testid="prompt-builder">
      <fieldset className="stack">
        <legend className="h4">Presets (kept only in this browser)</legend>
        <div className="inline">
          <label htmlFor={`${id}-preset`} className="sr-only">
            Preset
          </label>
          <select id={`${id}-preset`} value={chosen} onChange={(e) => setChosen(e.target.value)}>
            <option value="">Choose a preset…</option>
            {presets.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name}
              </option>
            ))}
          </select>
          <button type="button" className="btn" onClick={apply} disabled={!chosen}>
            Apply
          </button>
          <button type="button" className="btn btn-quiet" onClick={remove} disabled={!chosen}>
            Delete
          </button>
        </div>
        <div className="inline">
          <label htmlFor={`${id}-preset-name`}>Save these choices as</label>
          <input id={`${id}-preset-name`} value={presetName} maxLength={60} onChange={(e) => setPresetName(e.target.value)} />
          <button type="button" className="btn" onClick={save} disabled={!presetName.trim()}>
            Save preset
          </button>
        </div>
        <p role="status" aria-live="polite" className="muted">
          {presetStatus}
        </p>
      </fieldset>

      <div className="field">
        <label htmlFor={`${id}-goal`}>Goal</label>
        <input id={`${id}-goal`} value={plan.goal} maxLength={2000} placeholder="What this batch should achieve" onChange={(e) => set({ goal: e.target.value })} />
      </div>

      <div className="table-wrap">
        <table>
          <caption className="sr-only">Episodes per format</caption>
          <thead>
            <tr>
              <th scope="col">Format</th>
              <th scope="col">Episodes</th>
              {games ? (
                <>
                  <th scope="col">Approachable</th>
                  <th scope="col">Moderate</th>
                  <th scope="col">Challenging</th>
                  <th scope="col">Music</th>
                </>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {plan.scope.map((row) => {
              const format = formatOf(catalog, plan.project, row.format)
              const label = `${format?.name ?? row.format}${format?.game ? ` (${format.game})` : ''}`
              return (
                <tr key={row.format}>
                  <th scope="row">{label}</th>
                  <td>
                    <input
                      type="number"
                      inputMode="numeric"
                      min={0}
                      max={MAX_PER_FORMAT}
                      aria-label={`${label}: episodes`}
                      value={row.count}
                      onChange={(e) => setRow(row.format, toCount(e.target.value, MAX_PER_FORMAT))}
                    />
                  </td>
                  {games ? (
                    <>
                      {(['approachable', 'moderate', 'challenging'] as const).map((name, i) => (
                        <td key={name}>
                          <input
                            type="number"
                            inputMode="numeric"
                            min={0}
                            max={MAX_PER_FORMAT}
                            aria-label={`${label}: ${name}`}
                            value={row.mix[i]}
                            disabled={row.count === 0}
                            onChange={(e) => {
                              const mix: DifficultyMix = [...row.mix]
                              mix[i] = toCount(e.target.value, MAX_PER_FORMAT)
                              setRow(row.format, row.count, mix)
                            }}
                          />
                        </td>
                      ))}
                      <td>
                        <select
                          aria-label={`${label}: music`}
                          value={plan.music[row.format] ?? CALM}
                          disabled={row.count === 0}
                          onChange={(e) => set({ music: { ...plan.music, [row.format]: e.target.value } })}
                        >
                          <option value={CALM}>Calm rotation</option>
                          {bedsFor(catalog, plan.project, row.format).map((b) => (
                            <option key={b.id} value={b.id}>
                              {b.title}
                              {b.artist ? ` · ${b.artist}` : ''}
                            </option>
                          ))}
                        </select>
                      </td>
                    </>
                  ) : null}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="muted">Total: {totalEpisodes(plan)} episodes.</p>

      {games ? (
        <>
          <fieldset className="stack">
            <legend className="h4">Styles</legend>
            {plannedGames(catalog, plan).map((game) => (
              <div key={game} className="field">
                <label htmlFor={`${id}-style-${game}`}>{game}</label>
                <select id={`${id}-style-${game}`} value={plan.styles[game] ?? ''} onChange={(e) => set({ styles: { ...plan.styles, [game]: e.target.value } })}>
                  {stylesFor(catalog, game).map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.id}
                    </option>
                  ))}
                </select>
              </div>
            ))}
            <p className="hint">A new style or format is mode 2 (a template and a pilot first).</p>
          </fieldset>
          <div className="inline">
            <label htmlFor={`${id}-spares`}>Spares per format</label>
            <input
              id={`${id}-spares`}
              type="number"
              inputMode="numeric"
              min={0}
              max={MAX_SPARES}
              value={plan.spares}
              onChange={(e) => set({ spares: toCount(e.target.value, MAX_SPARES) })}
            />
          </div>
          <div className="field-check">
            <input id={`${id}-pilots`} type="checkbox" checked={plan.pilots} onChange={(e) => set({ pilots: e.target.checked })} />
            <label htmlFor={`${id}-pilots`}>Pilots first: one video per game, then Checkpoint 2</label>
          </div>
        </>
      ) : (
        <div className="field">
          <label htmlFor={`${id}-subjects`}>Subjects (one title or story idea per line)</label>
          <textarea id={`${id}-subjects`} rows={4} maxLength={2000} value={plan.subjects} onChange={(e) => set({ subjects: e.target.value })} />
        </div>
      )}

      <div className="field">
        <label htmlFor={`${id}-prefer`}>Prefer</label>
        <input id={`${id}-prefer`} value={plan.prefer} maxLength={2000} onChange={(e) => set({ prefer: e.target.value })} />
      </div>
      <div className="field">
        <label htmlFor={`${id}-avoid`}>Avoid</label>
        <input id={`${id}-avoid`} value={plan.avoid} maxLength={2000} onChange={(e) => set({ avoid: e.target.value })} />
      </div>
      <div className="field">
        <label htmlFor={`${id}-experiment`}>Experiment id (optional)</label>
        <input id={`${id}-experiment`} value={plan.experimentId} maxLength={64} placeholder="e.g. hooks-2026-11" onChange={(e) => set({ experimentId: e.target.value })} />
      </div>
      <div className="field">
        <label htmlFor={`${id}-notes`}>Things to try (one per line)</label>
        <textarea id={`${id}-notes`} rows={3} maxLength={2000} value={plan.notes} onChange={(e) => set({ notes: e.target.value })} />
      </div>
    </div>
  )
}
