import { useState } from 'react'
import { api } from '../../api/client'
import type { StorySettings, StorySettingsUpdate, StoryTier } from '../../api/types'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Loading } from '../../components/Loading'
import { ScreenHelp } from '../../components/ScreenHelp'
import { StatusBadge } from '../../components/StatusBadge'
import { useApi } from '../../hooks/useApi'
import { detectPreset, TIER_LABELS, usd } from '../../lib/storyJobs'

const MODEL_FIELDS = [
  ['llm_model', 'Text (script, story)'],
  ['image_model', 'Images (cast, sets)'],
  ['tts_model', 'Voice'],
] as const

/** Studio › Story settings (F20–F22): models and the video tier for the next runs; keys stay on the laptop (F23 dropped). */
export function StorySettingsView() {
  const settings = useApi(api.storySettings)
  const [saved, setSaved] = useState(false)
  return (
    <div className="stack-lg">
      <p>
        <a href="#/studio/jobs">← Story jobs</a>
      </p>
      <ScreenHelp id="storySettings" />
      <ErrorNotice error={settings.error} title="Story settings unavailable" />
      {settings.loading && !settings.data ? <Loading /> : null}
      {settings.data ? (
        <SettingsForm
          key={JSON.stringify(settings.data)}
          settings={settings.data}
          saved={saved}
          onEdit={() => setSaved(false)}
          onSaved={(next) => {
            settings.setData(next)
            setSaved(true)
          }}
        />
      ) : null}
    </div>
  )
}

function SettingsForm({ settings, saved, onEdit, onSaved }: { settings: StorySettings; saved: boolean; onEdit: () => void; onSaved: (s: StorySettings) => void }) {
  const [draft, setDraft] = useState({ ...settings.models, ...settings.video })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const preview: StorySettings = { ...settings, models: { llm_model: draft.llm_model, image_model: draft.image_model, tts_model: draft.tts_model }, video: { ...settings.video, active_tier: draft.active_tier } }
  const preset = detectPreset(preview)
  const changed = JSON.stringify(draft) !== JSON.stringify({ ...settings.models, ...settings.video })
  const set = (patch: Partial<typeof draft>) => {
    onEdit()
    setDraft((d) => ({ ...d, ...patch }))
  }
  const pickTier = (tier: StoryTier) => {
    const models = settings.tiers[tier] ?? []
    set({ active_tier: tier, active_model: models.some((m) => m.id === draft.active_model) ? draft.active_model : (models[0]?.id ?? draft.active_model) })
  }
  const applyPreset = (p: StorySettings['presets'][string]) => {
    const models = settings.tiers[p.tier] ?? []
    set({
      llm_model: p.llm_model,
      image_model: p.image_model,
      tts_model: p.tts_model,
      active_tier: p.tier,
      active_model: models.some((m) => m.id === draft.active_model) ? draft.active_model : (models[0]?.id ?? draft.active_model),
    })
  }
  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      const body: StorySettingsUpdate = { ...draft }
      onSaved(await api.storySaveSettings(body))
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <section className="card stack" aria-labelledby="story-presets">
        <h2 id="story-presets">
          Quality preset <StatusBadge tone={preset === 'custom' ? 'neutral' : 'info'} label={preset === 'custom' ? 'Custom' : preset[0]?.toUpperCase() + preset.slice(1)} />
        </h2>
        <div className="actions">
          {Object.entries(settings.presets).map(([id, p]) => (
            <button key={id} type="button" className="btn" aria-pressed={preset === id} onClick={() => applyPreset(p)}>
              {id[0]?.toUpperCase() + id.slice(1)}
            </button>
          ))}
        </div>
        <p className="hint">A preset sets the text, image and voice models and the video tier at once.</p>
      </section>

      <section className="card stack" aria-labelledby="story-models">
        <h2 id="story-models">Models</h2>
        {MODEL_FIELDS.map(([key, label]) => (
          <div key={key} className="field">
            <label htmlFor={`story-${key}`}>{label}</label>
            <select id={`story-${key}`} value={draft[key]} onChange={(e) => set({ [key]: e.target.value })}>
              {settings.choices[key].map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
        ))}
      </section>

      <section className="card stack" aria-labelledby="story-video">
        <h2 id="story-video">Video</h2>
        <div className="segmented" role="radiogroup" aria-label="Tier">
          {(['cheapest', 'recommended', 'high_fidelity'] as const).map((tier) => (
            <label key={tier} className="choice">
              <input type="radio" name="story-tier" checked={draft.active_tier === tier} onChange={() => pickTier(tier)} />
              <strong>{TIER_LABELS[tier]}</strong>
            </label>
          ))}
        </div>
        <ul className="choice-list" role="radiogroup" aria-label="Video model">
          {(settings.tiers[draft.active_tier] ?? []).map((m) => (
            <li key={m.id} className="choice" data-testid="story-model">
              <label className="field-check">
                <input type="radio" name="story-model" checked={draft.active_model === m.id} onChange={() => set({ active_model: m.id })} />
                <span>
                  <strong>{m.name}</strong> <span className="muted">· {m.provider}</span>
                  <br />
                  <span className="muted">
                    ${m.costPerSecondUsd}/s · {m.maxResolution} · {m.clipSeconds ? `${m.clipSeconds}s a shot` : `up to ${m.maxDurationSeconds}s`} ·{' '}
                    {m.audio ? 'audio' : 'no audio'}
                    {m.referenceImages ? ' · reference images' : ''} · about {usd(m.episodeUsd)} an episode (6 shots)
                  </span>
                  {m.description ? (
                    <>
                      <br />
                      {m.description}
                    </>
                  ) : null}
                </span>
              </label>
            </li>
          ))}
        </ul>
        <div className="field">
          <label htmlFor="story-max-budget">Budget per job (USD)</label>
          <input
            id="story-max-budget"
            type="number"
            min={0}
            max={1000}
            step={0.5}
            value={draft.max_budget}
            onChange={(e) => set({ max_budget: Number(e.target.value) })}
          />
        </div>
        <div className="field-check">
          <input id="story-downgrade" type="checkbox" checked={draft.auto_downgrade} onChange={(e) => set({ auto_downgrade: e.target.checked })} />
          <label htmlFor="story-downgrade">Switch to a cheaper model when a job nears its budget</label>
        </div>
      </section>

      <section className="card stack" aria-labelledby="story-keys">
        <h2 id="story-keys">Keys</h2>
        <p>Keys live only in the laptop&apos;s engines/story/.env and are never sent here.</p>
        <dl className="facts">
          {Object.entries(settings.keys).map(([k, v]) => (
            <div key={k} className="contents">
              <dt>{k}</dt>
              <dd>{v ? 'Set' : 'Missing'}</dd>
            </div>
          ))}
        </dl>
      </section>

      <ErrorNotice error={error} title="Settings not saved" />
      {saved ? (
        <p className="notice notice-info" role="status">
          Saved. The next run uses these settings.
        </p>
      ) : null}
      <div className="actions">
        <button type="button" className="btn btn-primary" disabled={busy || !changed || !(draft.max_budget >= 0)} onClick={() => void save()}>
          Save settings
        </button>
      </div>
    </>
  )

}
