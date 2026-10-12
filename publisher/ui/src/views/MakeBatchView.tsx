import { useId, useMemo, useState } from 'react'
import { api } from '../api/client'
import type { Catalog, NextBatchInfo } from '../api/types'
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
  buildFeedbackExport,
  feedbackFileName,
  feedbackJson,
  groupFeedback,
  tagLabel,
} from '../lib/nextBatch'
import { projectsInOrder } from '../lib/catalog'
import { accountRow, metricsSummary } from '../lib/postMetrics'
import { buildPlanBrief, buildPlanPrompt, defaultPlan, planProblems, type BatchPlan } from '../lib/promptBuilder'
import { copyText, saveTextFile } from '../lib/saveFile'
import { deviceTimeZone } from '../lib/time'
import { episodeHash, guideHash } from '../views'
import { AddBatchFlow } from './library/AddBatchFlow'
import { BatchNotesPanel } from './library/BatchNotesPanel'
import { FunnelTable } from './library/FunnelTable'
import { PostStatsPanel } from './library/PostStatsPanel'
import { MakeStep as Step } from '../components/MakeStep'
import { PlanMakeContent } from './studio/PlanMakeContent'
import { PromptBuilderForm } from './studio/PromptBuilderForm'

const MAC_FOLDER = 'cd ~/Personal/code_projects/StudioZero && claude'

/**
 * Studio › Make a batch, per catalog project. Scalargame (docs/PI_UI_REDESIGN_PLAN.md §4.7): the Mac step, shown in
 * the UI; steps 1, 2 and 4 are live on the Pi, step 3 is numbered instructions with a browser-local checklist, step 5
 * is the retro. Projects without games (Originals): PlanMakeContent.
 */
export function MakeBatchView({ project }: { project?: string | undefined }) {
  const catalog = useApi(api.catalog)
  const projects = catalog.data ? projectsInOrder(catalog.data) : []
  const chosen = projects.find((p) => p.id === project) ?? projects.find((p) => p.games?.length) ?? projects[0]
  return (
    <div className="stack-lg">
      <p className="review-nav">
        <a href="#/studio">← Studio</a>
      </p>
      <ScreenHelp id="make" />
      <ErrorNotice error={catalog.error} title="Studio catalog unavailable" />
      {catalog.data && chosen ? (
        <>
          <div className="chip-row" role="group" aria-label="Project">
            {projects.map((p) => (
              <a key={p.id} className="chip-btn" href={`#/studio/make?project=${encodeURIComponent(p.id)}`} aria-current={p.id === chosen.id ? 'page' : undefined}>
                {p.name}
              </a>
            ))}
          </div>
          {chosen.games?.length ? <ScalargameMake catalog={catalog.data} /> : <PlanMakeContent key={chosen.id} catalog={catalog.data} project={chosen} />}
        </>
      ) : catalog.loading ? (
        <Loading />
      ) : null}
    </div>
  )
}

function ScalargameMake({ catalog }: { catalog: Catalog }) {
  const next = useApi(api.nextBatch)
  // Only for fromCommit in feedback.json; a failure here is not shown.
  const update = useApi(() => api.updateStatus())
  const { dashboard, reload } = useJourney()
  const lastBatchId = dashboard?.standing?.lastBatch?.batchId ?? null
  return (
    <>
      <ErrorNotice error={next.error} title="Next batch unavailable" />
      {next.data ? (
        <MakeBatchContent
          key={next.data.nextBatchId}
          info={next.data}
          catalog={catalog}
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
    </>
  )
}


export function MakeBatchContent({
  info,
  catalog,
  fromCommit,
  onChanged,
  lastBatchId = null,
}: {
  info: NextBatchInfo
  catalog: Catalog
  fromCommit: string | null
  onChanged: () => void
  lastBatchId?: string | null
}) {
  const id = useId()
  const zone = deviceTimeZone()
  const [plan, setPlan] = useState<BatchPlan>(() => defaultPlan(catalog, 'scalargame', info.nextBatchId))
  const template = useMemo(() => buildPlanBrief(catalog, plan, info), [catalog, plan, info])
  // The brief follows the choices until the owner edits it by hand; Reset goes back to following them.
  const [edited, setEdited] = useState<string | null>(null)
  const brief = edited ?? template
  const problems = planProblems(catalog, plan)
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
    const ok = await copyText(buildPlanPrompt(catalog, plan, brief))
    started()
    setStatus(ok ? 'Prompt copied. Paste it into Claude Code on the Mac (step 3).' : 'Copy failed: select the brief and copy it by hand.')
  }
  const download = () => {
    const doc = buildFeedbackExport({ info, brief, fromCommit, exportedAt: new Date() })
    saveTextFile(fileName, feedbackJson(doc))
    started()
    setStatus(`Saved ${fileName}. On the Mac, put it in library/_inbox/ in the StudioZero folder.`)
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
              On the Mac, put it in <code>library/_inbox/</code> in the StudioZero folder (not in git; it may name answers).
            </p>
          </Step>

          <Step n={2} title="Write the brief" where="Pi">
            <p>Choose the mix from the formats, styles and music the studio has; the brief is prefilled from them, the open feedback and the last retro.</p>
            <PromptBuilderForm
              catalog={catalog}
              plan={plan}
              onChange={(next) => {
                setPlan(next)
                started()
              }}
            />
            <div className="actions">
              <RevealToggle
                revealed={showBrief}
                onToggle={setShowBrief}
                controls={`${id}-brief-body`}
                showLabel="Show brief (may contain answers)"
                hideLabel="Hide brief"
              />
              <button type="button" className="btn btn-quiet" onClick={() => setEdited(null)} disabled={edited === null}>
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
                      setEdited(e.target.value)
                      started()
                    }}
                    className="brief-text"
                  />
                </div>
              ) : null}
            </div>
            {problems.length ? (
              <div className="notice notice-warn" data-testid="plan-problems">
                <p>Fix these first:</p>
                <ul>
                  {problems.map((p) => (
                    <li key={p}>{p}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            <div className="actions">
              <button type="button" className="btn btn-primary" onClick={() => void copy()} disabled={problems.length > 0}>
                Copy prompt for Claude
              </button>
            </div>
            <p className="hint">The prompt ends with the fixed safety lines: nothing is finalized, uploaded or paid for without your OK.</p>
            <p role="status" aria-live="polite" className="muted">
              {status}
            </p>
          </Step>
        </div>

        <div className="stack-lg">
          <Step n={3} title="Let Claude make it" where="Mac" testId="make-checklist">
            <ol className="steps">
              <li>
                Open Terminal and start Claude in the StudioZero folder:
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
