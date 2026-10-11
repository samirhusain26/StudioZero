import type { LibraryEpisode, MeasuredMedia, Platform, PlatformEligibility } from '../../api/types'
import { PLATFORMS } from '../../api/types'
import { StatusBadge } from '../../components/StatusBadge'
import { formatBytes, formatDuration, formatFps, platformName, titleCase } from '../../lib/format'
import { EPISODE_STATUS } from '../../lib/labels'
import { episodeHash } from '../../views'

export function audioText(m: MeasuredMedia): string {
  if (m.audioStreams === 0 || !m.audioCodec) return 'Silent'
  const rate = m.audioSampleRate ? `${(m.audioSampleRate / 1000).toFixed(m.audioSampleRate % 1000 ? 1 : 0)} kHz` : 'unknown rate'
  const channels = m.audioChannels === 2 ? 'stereo' : m.audioChannels === 1 ? 'mono' : m.audioChannels ? `${m.audioChannels} channels` : 'unknown channels'
  return `${m.audioCodec.toUpperCase()} ${rate} ${channels}`
}

export function MediaFacts({ media }: { media: MeasuredMedia }) {
  return (
    <dl className="facts">
      <dt>Duration</dt>
      <dd>{formatDuration(media.durationSeconds)}</dd>
      <dt>Size</dt>
      <dd>{formatBytes(media.bytes)}</dd>
      <dt>Resolution</dt>
      <dd>{media.width && media.height ? `${media.width}×${media.height}` : 'unknown'}</dd>
      <dt>Frame rate</dt>
      <dd>{formatFps(media.fps)}</dd>
      <dt>Video</dt>
      <dd>
        {media.videoCodec ?? 'unknown'} {media.pixFmt ?? ''}
      </dd>
      <dt>Audio</dt>
      <dd>{audioText(media)}</dd>
      <dt>Fast-start</dt>
      <dd>{media.fastStart === null ? 'Not checked' : media.fastStart ? 'Yes' : 'No (moov after mdat)'}</dd>
    </dl>
  )
}

export function EligibilityList({ platforms }: { platforms: Record<Platform, PlatformEligibility> }) {
  return (
    <ul className="row-list">
      {PLATFORMS.map((p) => {
        const e = platforms[p]
        return (
          <li key={p} className="row-item">
            <span className="platform-name">{platformName(p)}</span>
            <StatusBadge tone={e.eligible ? 'good' : 'bad'} label={e.eligible ? 'Eligible' : 'Not eligible'} />
            {e.reason ? <span className="muted">{e.reason}</span> : null}
          </li>
        )
      })}
    </ul>
  )
}

/** One episode in the Library list: cover, question, three facts and its status. Tap anywhere to review it. */
export function EpisodeCard({ episode }: { episode: LibraryEpisode }) {
  const status = EPISODE_STATUS[episode.status]
  const creative = episode.episode.creative
  const question = creative?.question || creative?.hook || episode.questionId
  const facts = [titleCase(episode.game), episode.difficulty ? titleCase(episode.difficulty) : null, `rev ${episode.revision}`].filter(Boolean).join(' · ')
  return (
    <a className="card episode-card" href={episodeHash(episode.episodeId, episode.revision)} data-testid="episode-card">
      {episode.coverUrl ? (
        <img className="thumb-cover" src={episode.coverUrl} alt="" loading="lazy" width={54} height={96} />
      ) : (
        <span className="thumb-cover cover-missing" aria-hidden="true" />
      )}
      <span className="episode-card-body">
        <span className="episode-card-question">{question}</span>
        <span className="muted episode-card-facts">
          {facts} · {episode.episodeId}
        </span>
        <StatusBadge tone={status.tone} label={episode.problems.length ? 'Has problems' : episode.statusLabel || status.label} />
      </span>
    </a>
  )
}
