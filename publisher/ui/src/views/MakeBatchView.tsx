import { useId, useMemo, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type { NextBatchInfo } from '../api/types'
import { CopyBlock } from '../components/CopyBlock'
import { ErrorNotice } from '../components/ErrorNotice'
import { Loading } from '../components/Loading'
import { Markdown } from '../components/Markdown'
import { ConfirmDialog } from '../components/Modal'
import { RevealToggle } from '../components/RevealToggle'
import { ScreenHelp } from '../components/ScreenHelp'
import { StatusBadge } from '../components/StatusBadge'
import { Time } from '../components/Time'
import { useApi } from '../hooks/useApi'
import { useJourney } from '../hooks/useJourney'
import { formatBytes, platformName } from '../lib/format'
import { MAKE_CHECKPOINTS, readMake, writeMake, type CheckpointId, type MakeProgress } from '../lib/makeChecklist'
import {
  buildBriefTemplate,
  buildCopyPrompt,
  buildFeedbackExport,
  feedbackFileName,
  feedbackJson,
  groupFeedback,
  tagLabel,
} from '../lib/nextBatch'
import { accountRow, metricsSummary } from '../lib/postMetrics'
import { copyText, saveTextFile } from '../lib/saveFile'
import { deviceTimeZone } from '../lib/time'
import { episodeHash, guideHash } from '../views'
import { AddBatchFlow } from './library/AddBatchFlow'
import { BatchNotesPanel } from './library/BatchNotesPanel'
import { FunnelTable } from './library/FunnelTable'
import { PostStatsPanel } from './library/PostStatsPanel'

const MAC_FOLDER = 'cd ~/Personal/code_projects/scalargame/marketing && claude'

/**
 * Library › Make a batch (docs/PI_UI_REDESIGN_PLAN.md §4.7): the Mac step, shown in the UI. Steps 1, 2 and 4 are
 * live on the Pi; step 3 is numbered instructions with a browser-local checklist; step 5 is the retro.
 */
export function MakeBatchView() {
  const next = useApi(api.nextBatch)
  // Only for fromCommit in feedback.json; a failure here is not shown.
  const update = useApi(() => api.updateStatus())
  const { dashboard, reload } = useJourney()
  const lastBatchId = dashboard?.standing?.lastBatch?.batchId ?? null
  return (
    <div className="stack-lg">
      <p className="review-nav">
        <a href="#/library">← Library</a>
      </p>
      <ScreenHelp id="make" />
      <ErrorNotice error={next.error} title="Next batch unavailable" />
      {next.data ? (
        <MakeBatchContent
          key={next.data.nextBatchId}
          info={next.data}
          fromCommit={update.data?.runningCommit ?? null}
          lastBatchId={lastBatchId}
          onChanged={() => {
            next.reload()
            reload()
          }}
        />
      ) : next.loading ? (
        <Loading />
      ) : null}
    </div>
  )
}

function Step({ n, title, where, children, testId }: { n: number; title: string; where: 'Pi' | 'Mac'; children: ReactNode; testId?: string }) {
  const id = useId()
  return (
    <section className="card stack" aria-labelledby={id} data-testid={testId}>
      <h2 id={id} className="make-step-title">
        <span className="loop-num" aria-hidden="true">
          {n}
        </span>
        {title}
        <span className={`where where-${where.toLowerCase()}`}>{where === 'Mac' ? 'on the Mac' : 'here on the Pi'}</span>
      </h2>
      {children}
    </section>
  )
}

export function MakeBatchContent({
  info,
  fromCommit,
  onChanged,
  lastBatchId = null,
}: {
  info: NextBatchInfo
  fromCommit: string | null
  onChanged: () => void
  lastBatchId?: string | null
}) {
  const id = useId()
  const zone = deviceTimeZone()
  const template = useMemo(() => buildBriefTemplate(info), [info])
  const [brief, setBrief] = useState(template)
  const [status, setStatus] = useState('')
  const [showRetro, setShowRetro] = useState(false)
  const [showLastBrief, setShowLastBrief] = useState(false)
  const [showNotes, setShowNotes] = useState(false)
  const [showBrief, setShowBrief] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [markResult, setMarkResult] = useState<string | null>(null)
  const [markError, setMarkError] = useState<unknown>(null)
  const [progress, setProgress] = useState<MakeProgress>(() => readMake(info.nextBatchId))
  const groups = groupFeedback(info.openFeedback)
  const hasNotes = info.openFeedback.some((f) => f.note)
  const batchId = info.nextBatchId
  const fileName = feedbackFileName(batchId)

  const save = (next: MakeProgress) => {
    setProgress(next)
    writeMake(next)
  }
  const started = () => {
    if (!progress.started) save({ ...progress, started: true })
  }
  const tick = (checkpoint: CheckpointId, on: boolean) => {
    const checks = on ? [...new Set([...progress.checks, checkpoint])] : progress.checks.filter((c) => c !== checkpoint)
    save({ ...progress, started: true, checks: MAKE_CHECKPOINTS.map((c) => c.id).filter((c) => checks.includes(c)) })
  }

  const copy = async () => {
    const ok = await copyText(buildCopyPrompt(batchId, brief))
    started()
    setStatus(ok ? 'Prompt copied. Paste it into Claude Code on the Mac (step 3).' : 'Copy failed: select the brief and copy it by hand.')
  }
  const download = () => {
    const doc = buildFeedbackExport({ info, brief, fromCommit, exportedAt: new Date() })
    saveTextFile(fileName, feedbackJson(doc))
    started()
    setStatus(`Saved ${fileName}. On the Mac, put it in marketing/library/_inbox/.`)
  }
  const markUsed = async () => {
    setBusy(true)
    setMarkError(null)
    try {
      const result = await api.markFeedbackUsed(info.openFeedback.map((f) => ({ episodeId: f.episodeId, revision: f.revision })))
      setMarkResult(`Marked ${result.updated} note${result.updated === 1 ? '' : 's'} as used.`)
      onChanged()
    } catch (e) {
      setMarkError(e)
    } finally {
      setBusy(false)
      setConfirming(false)
    }
  }

  return (
    <>
      <p>
        Next batch: <code className="make-id">{batchId}</code>
      </p>
      <div className="make-layout">
        <div className="stack-lg">
          <Step n={1} title="Carry feedback over" where="Pi" testId="open-feedback">
            <p className="muted">
              {info.openFeedback.length} open feedback note{info.openFeedback.length === 1 ? '' : 's'} · last retro{' '}
              {info.lastRetro ? <Time iso={info.lastRetro.uploadedAt} zone={zone} /> : 'none'} · last brief{' '}
              {info.lastBrief ? <Time iso={info.lastBrief.uploadedAt} zone={zone} /> : 'none'}
            </p>
            <details className="disclosure">
              <summary>Read the open feedback ({info.openFeedback.length})</summary>
              {hasNotes ? (
                <div className="actions">
                  <RevealToggle
                    revealed={showNotes}
                    onToggle={setShowNotes}
                    controls={`${id}-fb-list`}
                    showLabel="Show notes (may contain answers)"
                    hideLabel="Hide notes"
                  />
                </div>
              ) : null}
              {groups.length === 0 ? (
                <p>No open feedback yet. Review episodes in the Library, tag what to keep or fix and add a note; it shows up here for the next brief.</p>
              ) : (
                <div id={`${id}-fb-list`} className="stack">
                  {groups.map((group) => (
                    <div key={group.batchId} className="stack">
                      <h3>Batch {group.batchId}</h3>
                      <ul className="row-list">
                        {group.items.map((item) => (
                          <li key={`${item.episodeId}@${item.revision}`} className="stack">
                            <p className="row-head">
                              <a href={episodeHash(item.episodeId, item.revision)}>
                                {item.episodeId} rev {item.revision}
                              </a>
                              <span className="muted">{[item.game, item.format, item.styleId].filter(Boolean).join(' · ')}</span>
                            </p>
                            {item.tags.length ? (
                              <p className="inline">
                                {item.tags.map((t) => (
                                  <StatusBadge key={t} tone="neutral" label={tagLabel(t)} />
                                ))}
                              </p>
                            ) : null}
                            {item.note ? showNotes ? <p className="exact-text">{item.note}</p> : <p className="muted">Note hidden</p> : null}
                            <p className="muted">
                              Updated <Time iso={item.updatedAt} zone={zone} />
                            </p>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
            </details>
            <details className="disclosure">
              <summary>Last retro and last brief</summary>
              {info.lastRetro ? (
                <div className="stack">
                  <p className="muted">
                    Retro: batch {info.lastRetro.batchId} · uploaded <Time iso={info.lastRetro.uploadedAt} zone={zone} /> · {formatBytes(info.lastRetro.bytes)}
                  </p>
                  <div className="actions">
                    <RevealToggle
                      revealed={showRetro}
                      onToggle={setShowRetro}
                      controls={`${id}-retro-body`}
                      showLabel="Show retro (may contain answers)"
                      hideLabel="Hide retro"
                    />
                  </div>
                  <div id={`${id}-retro-body`}>{showRetro ? <Markdown source={info.lastRetro.text} /> : null}</div>
                </div>
              ) : (
                <p>No retro uploaded yet. After a batch has posted, write the retro on the Mac and add RETRO.md in step 5.</p>
              )}
              {info.lastBrief ? (
                <div className="stack">
                  <p className="muted">
                    Brief: batch {info.lastBrief.batchId} · uploaded <Time iso={info.lastBrief.uploadedAt} zone={zone} /> · {formatBytes(info.lastBrief.bytes)}
                  </p>
                  <div className="actions">
                    <RevealToggle
                      revealed={showLastBrief}
                      onToggle={setShowLastBrief}
                      controls={`${id}-last-brief-body`}
                      showLabel="Show last brief (may contain answers)"
                      hideLabel="Hide last brief"
                    />
                  </div>
                  <div id={`${id}-last-brief-body`}>{showLastBrief ? <Markdown source={info.lastBrief.text} /> : null}</div>
                </div>
              ) : (
                <p>No brief uploaded yet. Add BRIEF.md to a batch in step 5.</p>
              )}
            </details>
            <details className="disclosure">
              <summary>How the posts did</summary>
              <PostStatsPanel zone={zone} onRead={onChanged} />
              <FunnelTable funnel={info.funnel} />
              <h3 className="h4">Accounts, last 7 days</h3>
              {info.accounts.length ? (
                <div className="table-wrap">
                  <table>
                    <caption className="sr-only">Followers and totals per account over the last 7 complete days</caption>
                    <thead>
                      <tr>
                        <th scope="col">Platform</th>
                        <th scope="col">Followers (7-day change)</th>
                        <th scope="col">Impressions</th>
                        <th scope="col">Engagements</th>
                        <th scope="col">Rate</th>
                        <th scope="col">Link clicks</th>
                      </tr>
                    </thead>
                    <tbody>
                      {info.accounts.map((a) => {
                        const row = accountRow(a)
                        return (
                          <tr key={a.platform}>
                            <th scope="row">
                              {platformName(a.platform)}
                              {row.note ? <div className="hint">{row.note}</div> : null}
                            </th>
                            <td>{row.followers}</td>
                            <td>{row.impressions}</td>
                            <td>{row.engagements}</td>
                            <td>{row.rate}</td>
                            <td>{row.clicks}</td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p>No account stats yet. They appear after the Pi's hourly stats timer has run (owner step in the guide).</p>
              )}
              <h3 className="h4">Performance</h3>
              {info.performance.length ? (
                <ul className="compact-list">
                  {info.performance.map((p, i) => (
                    <li key={`${p.platform}-${p.permalink ?? i}`}>
                      {platformName(p.platform)} · {p.status}
                      {p.at ? (
                        <>
                          {' '}
                          · <Time iso={p.at} zone={zone} />
                        </>
                      ) : null}
                      {p.permalink ? (
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
                <p>No posts with links yet. Once posts are confirmed, they appear here with their stats so the next brief can build on what worked.</p>
              )}
            </details>
            <div className="actions">
              <button type="button" className="btn" onClick={download}>
                Download {fileName}
              </button>
            </div>
            <p className="hint">
              On the Mac, put it in <code>marketing/library/_inbox/</code> (not in git; it may name answers).
            </p>
          </Step>

          <Step n={2} title="Write the brief" where="Pi">
            <p>Prefilled from the open feedback and the last retro. Say what to change, keep, try or avoid.</p>
            <div className="actions">
              <RevealToggle
                revealed={showBrief}
                onToggle={setShowBrief}
                controls={`${id}-brief-body`}
                showLabel="Show brief (may contain answers)"
                hideLabel="Hide brief"
              />
              <button type="button" className="btn btn-quiet" onClick={() => setBrief(template)} disabled={brief === template}>
                Reset to template
              </button>
            </div>
            <div id={`${id}-brief-body`}>
              {showBrief ? (
                <div className="field">
                  <label htmlFor={`${id}-brief-text`}>Brief (Markdown)</label>
                  <textarea
                    id={`${id}-brief-text`}
                    rows={18}
                    value={brief}
                    onChange={(e) => {
                      setBrief(e.target.value)
                      started()
                    }}
                    className="brief-text"
                  />
                </div>
              ) : null}
            </div>
            <div className="actions">
              <button type="button" className="btn btn-primary" onClick={() => void copy()}>
                Copy prompt for Claude
              </button>
            </div>
            <p role="status" aria-live="polite" className="muted">
              {status}
            </p>
          </Step>
        </div>

        <div className="stack-lg">
          <Step n={3} title="Let Claude make it" where="Mac" testId="make-checklist">
            <ol className="steps">
              <li>
                Open Terminal and start Claude in the marketing folder:
                <CopyBlock label="On the Mac" code={MAC_FOLDER} />
              </li>
              <li>
                Paste the prompt from step 2. Claude runs <code>/video-batch brief {batchId}</code> and stops at each checkpoint for your OK.
                Tick them off here as you go (this list is only kept in this browser):
              </li>
            </ol>
            <fieldset className="stack make-checks">
              <legend className="sr-only">Checkpoints for {batchId}</legend>
              {MAKE_CHECKPOINTS.map((c) => (
                <div key={c.id} className="field-check">
                  <input
                    id={`${id}-${c.id}`}
                    type="checkbox"
                    checked={progress.checks.includes(c.id)}
                    onChange={(e) => tick(c.id, e.target.checked)}
                  />
                  <label htmlFor={`${id}-${c.id}`}>
                    <strong>{c.label}</strong> <span className="muted">· {c.detail}</span>
                  </label>
                </div>
              ))}
            </fieldset>
            <p className="hint">
              Something off? Ask Claude for a revision before finalizing; after finalizing, make a new batch.{' '}
              <a href={guideHash('checkpoints')}>Checkpoints in the guide</a>
            </p>
          </Step>

          <Step n={4} title="Upload it" where="Pi">
            <p>
              Drop the finalized <code>library/{batchId}/</code> folder here, or choose it. After the upload, review the episodes in the Library.
            </p>
            <AddBatchFlow
              heading={null}
              bare
              onDone={() => {
                onChanged()
                window.location.hash = '/library'
              }}
            />
          </Step>

          <Step n={5} title="Retro, after posting" where="Mac">
            <ol className="steps">
              <li>
                Once the batch has posted, ask Claude for the retro:
                <CopyBlock label="On the Mac, in Claude" code={`/video-batch retro ${lastBatchId ?? '<batchId>'}`} />
              </li>
              <li>Add the RETRO.md it writes as the batch's retro note here, so the next brief can use it:</li>
            </ol>
            {lastBatchId ? <BatchNotesPanel batchId={lastBatchId} zone={zone} /> : <p className="muted">No Mac batch on the Pi yet.</p>}
            <div className="actions">
              <button type="button" className="btn" onClick={() => setConfirming(true)} disabled={info.openFeedback.length === 0}>
                Mark these notes as used ({info.openFeedback.length})
              </button>
            </div>
            <div role="status" aria-live="polite">
              {markResult ? <p className="notice notice-info">{markResult}</p> : null}
            </div>
            <ErrorNotice error={markError} title="Could not mark the notes" />
          </Step>
        </div>
      </div>

      {confirming ? (
        <ConfirmDialog
          title={`Mark ${info.openFeedback.length} note${info.openFeedback.length === 1 ? '' : 's'} as used?`}
          confirmLabel="Mark as used"
          busy={busy}
          onConfirm={() => void markUsed()}
          onCancel={() => setConfirming(false)}
        >
          <p>Do this after you copied the prompt and saved feedback.json. The notes stop appearing in the next brief.</p>
        </ConfirmDialog>
      ) : null}
    </>
  )
}
