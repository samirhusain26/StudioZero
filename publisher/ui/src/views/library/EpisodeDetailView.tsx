import { useId, useState, type ReactNode } from 'react'
import { api } from '../../api/client'
import type { BatchNote, EpisodeDetail, LibraryEpisode } from '../../api/types'
import { CAPTION_PLATFORMS, COMMENT_PLATFORMS } from '../../api/types'
import { ActionBar } from '../../components/ActionBar'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Loading } from '../../components/Loading'
import { Markdown } from '../../components/Markdown'
import { Modal } from '../../components/Modal'
import { RevealToggle } from '../../components/RevealToggle'
import { ScreenHelp } from '../../components/ScreenHelp'
import { StatusBadge } from '../../components/StatusBadge'
import { Time } from '../../components/Time'
import { useApi } from '../../hooks/useApi'
import { DESKTOP, useMediaQuery } from '../../hooks/useMediaQuery'
import { canApprove, listEpisodes, position, readListState } from '../../lib/libraryList'
import { metricsSummary } from '../../lib/postMetrics'
import { checkText, correctChoiceKey, engineText, httpsUrl, num, readEpisode, rec, str, strings, type Rec } from '../../lib/episodeView'
import { formatBytes, formatDuration, formatFps, platformName, shortHash, titleCase } from '../../lib/format'
import { EPISODE_STATUS, ledgerStatus } from '../../lib/labels'
import { deviceTimeZone } from '../../lib/time'
import { episodeHash } from '../../views'
import { useContentActions } from './ContentActions'
import { EligibilityList, MediaFacts } from './EpisodeCard'
import { FeedbackEditor } from './FeedbackEditor'

interface Neighbours {
  index: number
  total: number
  previous: LibraryEpisode | null
  next: LibraryEpisode | null
}

/** Review one episode (`#/library/episode/<id>/<rev>`): watch, approve, leave feedback, go to the next. */
export function EpisodeDetailView({ episodeId, revision }: { episodeId: string; revision: number }) {
  const detail = useApi(() => api.episodeDetail(episodeId, revision), `${episodeId}@${revision}`)
  // The library entry supplies the tokenized player/cover URLs, measured media and the list Next/Previous walk.
  const library = useApi(api.library)
  const entry = library.data?.episodes.find((e) => e.episodeId === episodeId && e.revision === revision)
  const zone = library.data?.displayTimezone ?? deviceTimeZone()
  const list = library.data ? listEpisodes(library.data, readListState(), { episodeId, revision }) : []
  const where = position(list, episodeId, revision)
  const changed = () => {
    library.reload()
    detail.reload()
  }
  return (
    <div className="review-layout">
      {list.length ? (
        <nav className="review-list card" aria-label="Episodes in this list">
          <ol className="row-list">
            {list.map((e) => (
              <li key={`${e.episodeId}@${e.revision}`}>
                <a
                  className="review-list-item"
                  href={episodeHash(e.episodeId, e.revision)}
                  aria-current={e.episodeId === episodeId && e.revision === revision ? 'page' : undefined}
                >
                  <span>{readEpisode(e.episode as unknown as Rec).question || e.episodeId}</span>
                  <StatusBadge tone={EPISODE_STATUS[e.status].tone} label={e.statusLabel || EPISODE_STATUS[e.status].label} />
                </a>
              </li>
            ))}
          </ol>
        </nav>
      ) : null}
      <div className="stack-lg review-main">
        <p className="review-nav">
          <a href="#/library">← Library</a>
          {where.index >= 0 ? (
            <span className="muted">
              {where.index + 1} of {where.total}
            </span>
          ) : null}
          {where.previous ? <a href={episodeHash(where.previous.episodeId, where.previous.revision)}>← Previous</a> : null}
        </p>
        <ScreenHelp id="episode" />
        <ErrorNotice error={detail.error} title="Episode unavailable" />
        {detail.data ? (
          <EpisodeDetailContent episodeId={episodeId} revision={revision} detail={detail.data} entry={entry} zone={zone} neighbours={where} onChanged={changed} />
        ) : detail.loading ? (
          <Loading />
        ) : null}
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd className="exact-text">{children}</dd>
    </div>
  )
}

export function EpisodeDetailContent({
  episodeId,
  revision,
  detail,
  entry,
  zone,
  neighbours = null,
  onChanged = () => {},
}: {
  episodeId: string
  revision: number
  detail: EpisodeDetail
  entry?: LibraryEpisode | undefined
  zone: string
  neighbours?: Neighbours | null
  onChanged?: () => void
}) {
  const id = useId()
  // Spoiler-safe by default; the component is keyed per episode route, so this resets on navigation.
  const [revealed, setRevealed] = useState(false)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const desktop = useMediaQuery(DESKTOP)
  const actions = useContentActions(onChanged)
  const view = readEpisode(detail.episode)
  const correct = revealed ? correctChoiceKey(view) : null
  const pub = view.publication ?? {}
  const captions = rec(pub.captions) ?? {}
  const firstComment = rec(pub.firstComment) ?? {}
  const youtube = rec(pub.youtube)
  const poll = rec(pub.poll)
  const answerReply = rec(pub.answerReply)
  const eligibility = view.eligibility ?? {}
  const status = entry ? EPISODE_STATUS[entry.status] : null
  const answerId = `${id}-answer`
  const approvable = canApprove(entry)
  const next = neighbours?.next ?? null
  const editor = <FeedbackEditor episodeId={episodeId} revision={revision} initial={detail.feedback} zone={zone} />
  const duration = num(view.video?.durationSeconds)

  return (
    <>
      <section className="stack review-hero" aria-labelledby={`${id}-h`} data-testid="episode-question">
        {entry?.videoUrl ? (
          <video
            className="player review-player"
            controls
            muted
            playsInline
            preload="metadata"
            src={entry.videoUrl}
            {...(entry.coverUrl ? { poster: entry.coverUrl } : {})}
            aria-label={`Video ${episodeId}`}
          />
        ) : (
          <p className="player review-player cover-missing">
            {entry?.videoRemovedAt ? 'Posted; video removed to free space (cover kept)' : 'The player appears once the video is on the Pi.'}
          </p>
        )}
        <h2 id={`${id}-h`} className="review-question">
          {view.question || view.hook || episodeId}
        </h2>
        <p className="muted">
          {[entry?.project, view.game !== entry?.project ? view.game : null, view.difficulty].filter(Boolean).map((v) => titleCase(v as string)).join(' · ')}
          {view.format ? ` · ${view.format}` : ''}
          {entry ? ` · ${engineText(entry)}` : ''}
          {duration ? ` · ${formatDuration(duration)}` : ''} · rev {revision} · batch {detail.batchId} · {episodeId}
        </p>
        {view.hook && view.question && view.hook !== view.question ? <p className="exact-text">{view.hook}</p> : null}
        {view.clues.length ? (
          <ol className="steps">
            {view.clues.map((clue, i) => (
              <li key={`${i}-${clue}`}>{clue}</li>
            ))}
          </ol>
        ) : null}
        {view.choices.length ? (
          <ul className="choice-list">
            {view.choices.map((c) => (
              <li key={c.key} className={c.key === correct ? 'choice choice-correct' : 'choice'}>
                <strong>{c.key}</strong> {c.label}
                {c.key === correct ? <StatusBadge tone="good" label="Correct" className="choice-badge" /> : null}
              </li>
            ))}
          </ul>
        ) : null}
        <p className="inline">
          {status && entry ? <StatusBadge tone={status.tone} label={entry.statusLabel || status.label} /> : null}
          {detail.approval ? (
            <StatusBadge tone={detail.approval.status === 'approved' ? 'good' : 'neutral'} label={`Approval: ${titleCase(detail.approval.status)}`} />
          ) : (
            <StatusBadge tone="neutral" label="Not approved" />
          )}
          {detail.approval?.at ? (
            <span className="muted">
              <Time iso={detail.approval.at} zone={zone} />
            </span>
          ) : null}
        </p>
        {entry?.problems.length ? (
          <div className="notice notice-error">
            <p>
              <strong>Validation problems</strong> (cannot be approved)
            </p>
            <ul className="problem-list">
              {entry.problems.map((p, i) => (
                <li key={`${p.path}-${i}`}>
                  {p.message} <code className="muted">{p.path}</code>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <ActionBar label="Review actions">
        <button type="button" className="btn btn-primary" disabled={!approvable} onClick={() => entry && actions.ask('approve', [entry])}>
          {entry?.status === 'approved' ? 'Approved ✓' : 'Approve'}
        </button>
        <button type="button" className="btn" aria-haspopup={desktop ? undefined : 'dialog'} onClick={() => (desktop ? document.getElementById(`${id}-fb`)?.scrollIntoView({ block: 'start' }) : setFeedbackOpen(true))}>
          Feedback
        </button>
        {next ? (
          <a className="btn" href={episodeHash(next.episodeId, next.revision)}>
            Next →
          </a>
        ) : (
          <a className="btn" href="#/library" aria-label="Done: back to the Library">
            Done →
          </a>
        )}
      </ActionBar>
      {actions.status}
      {desktop ? <div id={`${id}-fb`}>{editor}</div> : null}
      {feedbackOpen && !desktop ? (
        <Modal title="Feedback" variant="sheet" onClose={() => setFeedbackOpen(false)}>
          {editor}
        </Modal>
      ) : null}

      <div className="card stack">
        <details className="disclosure">
          <summary>Posts and captions</summary>
          {detail.posts.length ? (
            <ul className="compact-list">
              {detail.posts.map((p, i) => (
                <li key={`${p.platform}-${p.at ?? i}`}>
                  {platformName(p.platform)} · {p.status}
                  {p.at ? (
                    <>
                      {' '}
                      · <Time iso={p.at} zone={zone} />
                    </>
                  ) : null}
                  {p.permalink && httpsUrl(p.permalink) ? (
                    <>
                      {' '}
                      ·{' '}
                      <a href={p.permalink} target="_blank" rel="noopener noreferrer">
                        Open post
                      </a>
                    </>
                  ) : null}
                  {metricsSummary(p.metrics) ? <div className="hint">{metricsSummary(p.metrics)}</div> : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Not posted yet.</p>
          )}
          <dl className="text-list">
            {CAPTION_PLATFORMS.map((p) => {
              const text = str(captions[p])
              return text ? (
                <Field key={p} label={`${platformName(p)} caption`}>
                  {text}
                </Field>
              ) : null
            })}
            {youtube ? (
              <>
                <Field label="YouTube title">{str(youtube.title) ?? '—'}</Field>
                <Field label="YouTube description">{str(youtube.description) ?? '—'}</Field>
              </>
            ) : null}
            {str(pub.altText) ? <Field label="Alt text">{str(pub.altText)}</Field> : null}
            {strings(pub.hashtags).length ? <Field label="Hashtags">{strings(pub.hashtags).join(' ')}</Field> : null}
            {strings(pub.credits).length ? <Field label="Credits">{strings(pub.credits).join('; ')}</Field> : null}
            {poll ? (
              <Field label="Poll">
                {str(poll.question) ?? ''} — {strings(poll.options).join(' / ')}
              </Field>
            ) : null}
            {COMMENT_PLATFORMS.map((p) => {
              const text = str(firstComment[p])
              return text ? (
                <Field key={`fc-${p}`} label={`${platformName(p)} first comment`}>
                  {text}
                </Field>
              ) : null
            })}
            {str(pub.deepLink) ? (
              <Field label="Link">
                {str(pub.deepLink)} <span className="muted">(campaign {str(pub.utmCampaign) ?? '—'})</span>
              </Field>
            ) : null}
          </dl>
          {answerReply && !revealed ? <p className="hint">This episode has an answer reply; it shows with Reveal answer.</p> : null}
        </details>

        <details className="disclosure">
          <summary>Answer and evidence</summary>
          <div className="actions">
            <RevealToggle revealed={revealed} onToggle={setRevealed} controls={answerId} />
            {!revealed ? <span className="muted">Answer, explanation, sources and batch notes are hidden.</span> : null}
          </div>
          <div id={answerId} data-testid="answer-area">
            {revealed ? (
              <dl className="text-list">
                <Field label="Answer">{view.answer ?? '—'}</Field>
                {view.answerAliases.length ? <Field label="Also accepted">{view.answerAliases.join(', ')}</Field> : null}
                {view.explanation ? <Field label="Explanation">{view.explanation}</Field> : null}
                {view.questionId ? (
                  <Field label="Question id">
                    <code>{view.questionId}</code>
                  </Field>
                ) : null}
                {answerReply ? (
                  <Field label={`Answer reply (after ${num(answerReply.delayHours) ?? '?'} h)`}>{str(answerReply.text) ?? '—'}</Field>
                ) : null}
              </dl>
            ) : null}
          </div>
          <dl className="facts">
            <dt>Reviewer</dt>
            <dd>{view.reviewer ?? '—'}</dd>
            <dt>Sources</dt>
            <dd>{view.sources.length}</dd>
          </dl>
          {revealed ? (
            <>
              {view.sources.length ? (
                <ul className="compact-list">
                  {view.sources.map((src, i) => {
                    const url = httpsUrl(src.url)
                    return (
                      <li key={`${i}-${src.url ?? src.title}`}>
                        {url ? (
                          <a href={url} target="_blank" rel="noopener noreferrer">
                            {src.title}
                          </a>
                        ) : (
                          src.title
                        )}
                        {src.retrieved ? <span className="muted"> · retrieved {src.retrieved}</span> : null}
                      </li>
                    )
                  })}
                </ul>
              ) : null}
              {view.checks.length ? (
                <dl className="facts">
                  {view.checks.map(([key, value]) => (
                    <div key={key} className="contents">
                      <dt>{key}</dt>
                      <dd>
                        <code>{checkText(value)}</code>
                      </dd>
                    </div>
                  ))}
                </dl>
              ) : null}
            </>
          ) : (
            <p className="hint">Sources and checks often name the answer, so they show with Reveal answer.</p>
          )}
        </details>

        {entry ? <MadeWith entry={entry} /> : null}

        {entry ? (
          <details className="disclosure">
            <summary>Platform eligibility</summary>
            <EligibilityList platforms={entry.platforms} />
          </details>
        ) : null}

        <details className="disclosure">
          <summary>Measured on the Pi</summary>
          {entry?.media ? <MediaFacts media={entry.media} /> : <p className="muted">Measured once the video is on the Pi.</p>}
          <dl className="facts">
            {view.video ? (
              <>
                <dt>Video file</dt>
                <dd>
                  <code>{str(view.video.file) ?? '—'}</code> ({formatBytes(num(view.video.bytes))}, {formatFps(str(view.video.fps))})
                </dd>
                <dt>Video sha256</dt>
                <dd>
                  <code>{shortHash(str(view.video.sha256), 12)}</code>
                </dd>
              </>
            ) : null}
            {view.cover ? (
              <>
                <dt>Cover file</dt>
                <dd>
                  <code>{str(view.cover.file) ?? '—'}</code> ({formatBytes(num(view.cover.bytes))})
                </dd>
              </>
            ) : null}
            <dt>Style</dt>
            <dd>
              <code>{view.styleId ?? '—'}</code>
              {view.experimentId ? ` · experiment ${view.experimentId}${view.variantId ? ` / ${view.variantId}` : ''}` : ''}
            </dd>
            <dt>Music</dt>
            <dd>{view.music ? `${view.music.trackId ?? 'unknown track'} (${view.music.license ?? 'licence not recorded'})` : 'None'}</dd>
            <dt>Eligibility</dt>
            <dd>
              {str(eligibility.status) ? titleCase(str(eligibility.status) as string) : '—'} · not before {str(eligibility.notBefore) ?? '—'} ·
              review by {str(eligibility.reviewBy) ?? '—'} · expires {str(eligibility.expiresAt) ?? '—'}
            </dd>
          </dl>
        </details>

        <details className="disclosure">
          <summary>Batch notes (BRIEF / RETRO)</summary>
          <NoteMeta label="BRIEF.md" note={detail.notes.brief} zone={zone} />
          <NoteMeta label="RETRO.md" note={detail.notes.retro} zone={zone} />
          {revealed ? (
            <>
              {detail.notes.brief ? (
                <details>
                  <summary>BRIEF.md</summary>
                  <Markdown source={detail.notes.brief.text} />
                </details>
              ) : null}
              {detail.notes.retro ? (
                <details>
                  <summary>RETRO.md</summary>
                  <Markdown source={detail.notes.retro.text} />
                </details>
              ) : null}
            </>
          ) : detail.notes.brief || detail.notes.retro ? (
            <p className="hint">Notes may contain answers; they show with Reveal answer.</p>
          ) : null}
        </details>

        {entry ? (
          <details className="disclosure">
            <summary>History (approvals, duplicates)</summary>
            {entry.approvals.length === 0 ? <p>No approvals recorded.</p> : null}
            <ul>
              {entry.approvals.map((a) => (
                <li key={a.id}>
                  {a.action === 'approve' ? 'Approved' : 'Withdrawn'} by {a.reviewer}, <Time iso={a.at} zone={zone} />
                  {a.note ? ` — ${a.note}` : ''}
                  {entry.currentApproval?.id === a.id ? ' (current)' : ''}
                </li>
              ))}
            </ul>
            {entry.variants.length ? <p>Variants sharing this question: {entry.variants.join(', ')}</p> : null}
            {entry.postedOn.length ? (
              <ul>
                {entry.postedOn.map((p) => (
                  <li key={`${p.platform}-${p.accountId}-${p.slotUtc}`}>
                    {platformName(p.platform)} account <code>{p.accountId}</code>: {ledgerStatus(p.status).label}, <Time iso={p.slotUtc} zone={zone} />
                  </li>
                ))}
              </ul>
            ) : null}
          </details>
        ) : null}

        {entry ? (
          <details className="disclosure">
            <summary>More actions</summary>
            <div className="actions">
              {entry.status === 'approved' ? (
                <button type="button" className="btn" onClick={() => actions.ask('withdraw', [entry])}>
                  Withdraw approval
                </button>
              ) : null}
              {entry.deletable && !entry.inManifest ? (
                <button type="button" className="btn btn-danger" onClick={() => actions.ask('delete', [entry])}>
                  Delete upload
                </button>
              ) : null}
            </div>
            {entry.inManifest ? <p className="muted">In an approved manifest: kept read-only.</p> : null}
            <p className="muted">
              Video <code>{shortHash(entry.videoSha256)}</code> · cover <code>{shortHash(entry.coverSha256)}</code> · metadata{' '}
              <code>{shortHash(entry.metadataSha256)}</code>
            </p>
          </details>
        ) : null}
      </div>
      {actions.dialog}
    </>
  )
}

function NoteMeta({ label, note, zone }: { label: string; note: BatchNote | null; zone: string }) {
  return (
    <p className="muted">
      {label}:{' '}
      {note ? (
        <>
          uploaded <Time iso={note.uploadedAt} zone={zone} /> · {formatBytes(note.bytes)}
        </>
      ) : (
        'not uploaded (add it in Library → Batches → Notes)'
      )}
    </p>
  )
}

/** How the episode was made: engine, renderer, models, cost, AI disclosure and every credited asset (contract v2). */
function MadeWith({ entry }: { entry: LibraryEpisode }) {
  const d = entry.disclosure
  return (
    <details className="disclosure" data-testid="made-with">
      <summary>Made with</summary>
      <dl className="facts">
        <dt>Project</dt>
        <dd>{titleCase(entry.project)}</dd>
        <dt>Engine</dt>
        <dd>{engineText(entry)}</dd>
        <dt>Renderer</dt>
        <dd>{entry.renderer === 'web' ? 'Browser export (Studio)' : entry.renderer === 'render.sh' ? 'Mac (render.sh)' : 'Not recorded'}</dd>
        {entry.models.length ? (
          <>
            <dt>Models</dt>
            <dd>{entry.models.map((m) => `${m.role}: ${m.id}`).join(' · ')}</dd>
          </>
        ) : null}
        <dt>Cost</dt>
        <dd>{entry.costUsd === null ? 'Not recorded' : `$${entry.costUsd.toFixed(2)}`}</dd>
        <dt>AI content</dt>
        <dd>
          {d === null
            ? 'Not declared (contract v1): no AI label is applied'
            : d.aiGenerated
              ? `Yes (${d.aiKinds.join(', ')})${d.realisticSynthetic ? ', realistic synthetic' : ''}: AI labels are applied where the platform supports them`
              : 'No'}
          {d?.note ? <span className="block muted">{d.note}</span> : null}
        </dd>
      </dl>
      {entry.credits.length ? (
        <ul className="compact-list" data-testid="credits">
          {entry.credits.map((c, i) => {
            const url = httpsUrl(c.sourceUrl)
            return (
              <li key={`${i}-${c.title}`}>
                <span className="muted">{c.kind}</span> {url ? <a href={url} target="_blank" rel="noopener noreferrer">{c.title}</a> : c.title}
                {c.creator ? ` · ${c.creator}` : ''}
                {c.license ? ` · ${c.license}` : ''}
                {c.attribution ? <span className="block muted">{c.attribution}</span> : null}
              </li>
            )
          })}
        </ul>
      ) : (
        <p className="muted">No credits recorded.</p>
      )}
    </details>
  )
}
