import { useState } from 'react'
import { api, storyRenderUrl } from '../../api/client'
import type { StoryRender } from '../../api/types'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Loading } from '../../components/Loading'
import { ScreenHelp } from '../../components/ScreenHelp'
import { useApi } from '../../hooks/useApi'
import { formatBytes, formatDuration } from '../../lib/format'
import { routeLabel, usd } from '../../lib/storyJobs'

/** Studio › Story renders (F19): every finished story video on the laptop, from its render.json. */
export function StoryRendersView() {
  const renders = useApi(api.storyRenders)
  return (
    <div className="stack-lg">
      <p>
        <a href="#/studio/jobs">← Story jobs</a>
      </p>
      <ScreenHelp id="renders" />
      <ErrorNotice error={renders.error} title="Renders unavailable" />
      {renders.loading && !renders.data ? <Loading /> : null}
      {renders.data?.renders.length === 0 ? <p className="muted">No finished story videos on the laptop yet.</p> : null}
      <div className="episode-grid">
        {renders.data?.renders.map((r) => <RenderCard key={r.id} render={r} />)}
      </div>
    </div>
  )
}

function credits(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value
    .map((c) => {
      if (!c || typeof c !== 'object') return String(c)
      const { kind, title, creator, license } = c as Record<string, unknown>
      return [kind, title, creator, license].filter((v) => typeof v === 'string' && v).join(' · ')
    })
    .filter(Boolean)
    .slice(0, 8)
}

function RenderCard({ render }: { render: StoryRender }) {
  const [play, setPlay] = useState(false)
  const video = storyRenderUrl(render.id, 'video.mp4')
  const lines = credits(render.credits)
  return (
    <section className="card stack" aria-label={render.episodeId ?? render.id} data-testid="story-render">
      {play ? (
        <video className="player" src={video} controls autoPlay playsInline preload="metadata" />
      ) : (
        <button type="button" className="btn" onClick={() => setPlay(true)}>
          Play
        </button>
      )}
      <p className="row-head">
        <strong className="break">{render.episodeId ?? render.id}</strong>
      </p>
      <dl className="facts">
        <dt>Kind</dt>
        <dd>{routeLabel(render.route ?? '')}</dd>
        <dt>Made</dt>
        <dd>{render.createdAt ? new Date(render.createdAt).toLocaleString() : '—'}</dd>
        <dt>Video</dt>
        <dd>
          {[render.video?.durationSeconds ? formatDuration(render.video.durationSeconds) : null, render.video?.bytes ? formatBytes(render.video.bytes) : null]
            .filter(Boolean)
            .join(' · ') || '—'}
        </dd>
        <dt>Cost</dt>
        <dd>{render.costUsd === null || render.costUsd === undefined ? 'Not recorded' : usd(render.costUsd)}</dd>
      </dl>
      {lines.length ? (
        <details>
          <summary>Credits</summary>
          <ul className="plain-list">
            {lines.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </details>
      ) : null}
      <p>
        <a href={video} download>
          Download
        </a>
      </p>
    </section>
  )
}
