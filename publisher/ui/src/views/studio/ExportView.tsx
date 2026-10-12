import { Player } from '@remotion/player'
import { useCallback, useEffect, useId, useMemo, useRef, useState, type ComponentType } from 'react'
import { api } from '../../api/client'
import type { MotionManifest } from '../../api/types'
import { describeError, ErrorNotice } from '../../components/ErrorNotice'
import { Loading } from '../../components/Loading'
import { ConfirmDialog } from '../../components/Modal'
import { ScreenHelp } from '../../components/ScreenHelp'
import { StatusBadge } from '../../components/StatusBadge'
import { useApi } from '../../hooks/useApi'
import { formatBytes } from '../../lib/format'
import { saveBlob } from '../../lib/saveFile'
import { applyFailure, applyProgress, applyResult, initialUploadState, markUploading, uploadSummary, type UploadState } from '../../lib/uploadPlan'
import { parseBundle, type JobBundle, type JobInput } from '../../motion/bundle'
import { checkDevice, exportEpisode, FPS, HEIGHT, loadKit, WIDTH, type DeviceCheck, type ExportPhase } from '../../motion/engine'
import { episodeRows, isPhone, readyToPackage, remaining, STATUS_LABELS, type EpisodeRow } from '../../motion/exportState'
import { openMotionStore, type MotionStore } from '../../motion/store'
import { packageWebBatch, webRenderJson } from '../../motion/webPackage'

const PHASES: Record<ExportPhase, string> = { audio: 'Mixing audio', master: 'Mastering audio', video: 'Rendering video', qa: 'Checking the file', cover: 'Making the cover' }

/** Hold the screen awake while exporting where the browser allows it (phones dim and suspend otherwise). */
async function wakeLock(): Promise<{ release: () => Promise<void> } | null> {
  try {
    const nav = navigator as Navigator & { wakeLock?: { request: (t: 'screen') => Promise<{ release: () => Promise<void> }> } }
    return (await nav.wakeLock?.request('screen')) ?? null
  } catch {
    return null
  }
}

function statusTone(row: EpisodeRow): 'good' | 'warn' | 'bad' | 'neutral' {
  return row.status === 'passed' ? 'good' : row.status === 'failed' ? 'bad' : row.status === 'pending' ? 'neutral' : 'warn'
}

/**
 * Studio › Export (lazy chunk; docs/STUDIO_PLAN.md §1 decision 8): preview and export a Scalargame batch on this
 * device from its job bundle (engines/motion/pipeline/web-jobs.mjs), then package it and, with the owner's
 * confirmation, finalize and upload it to this Pi, which validates everything again.
 */
export default function ExportView() {
  const manifest = useApi(api.motionManifest)
  const update = useApi(() => api.updateStatus())
  const [store, setStore] = useState<MotionStore | null>(null)
  const [device, setDevice] = useState<DeviceCheck | null>(null)
  useEffect(() => {
    void openMotionStore().then(setStore)
    void checkDevice().then(setDevice)
  }, [])
  return (
    <div className="stack-lg">
      <p className="review-nav">
        <a href="#/studio">← Studio</a>
      </p>
      <ScreenHelp id="export" />
      <ErrorNotice error={manifest.error} title="Motion assets unavailable" />
      {manifest.data && store ? (
        <ExportContent manifest={manifest.data} store={store} device={device} commit={update.data?.runningCommit ?? null} />
      ) : manifest.loading || !store ? (
        <Loading />
      ) : null}
    </div>
  )
}

export function ExportContent({ manifest, store, device, commit }: { manifest: MotionManifest; store: MotionStore; device: DeviceCheck | null; commit: string | null }) {
  const id = useId()
  const assets = useMemo(() => new Set(Object.keys(manifest.files)), [manifest])
  const [bundle, setBundle] = useState<JobBundle | null>(null)
  const [problems, setProblems] = useState<string[]>([])
  const [rows, setRows] = useState<EpisodeRow[]>([])
  const [busy, setBusy] = useState<{ episodeId: string; phase: ExportPhase; fraction: number } | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [uploads, setUploads] = useState<UploadState | null>(null)
  const [uploadError, setUploadError] = useState<unknown>(null)
  const [uploading, setUploading] = useState(false)
  const cancel = useRef<AbortController | null>(null)
  const phone = isPhone(navigator as never, typeof matchMedia === 'function' && matchMedia('(pointer: coarse) and (max-width: 900px)').matches)

  const refresh = useCallback(
    async (b: JobBundle) => setRows(episodeRows(b, await store.getExports(b.batchId), await store.running(b.batchId))),
    [store],
  )

  useEffect(() => {
    void (async () => {
      const saved = await store.getBundle()
      if (!saved) return
      const parsed = parseBundle(saved.text, assets)
      if (parsed.bundle) {
        setBundle(parsed.bundle)
        await refresh(parsed.bundle)
      }
    })()
  }, [store, assets, refresh])

  const open = async (file: File) => {
    setProblems([])
    const parsed = parseBundle(await file.text(), assets)
    if (!parsed.bundle) return setProblems(parsed.problems)
    await store.putBundle({ batchId: parsed.bundle.batchId, text: JSON.stringify(parsed.bundle), savedAt: new Date().toISOString() })
    setBundle(parsed.bundle)
    setUploads(null)
    await refresh(parsed.bundle)
  }

  const runExports = async (ids: string[]) => {
    if (!bundle) return
    setError(null)
    const controller = new AbortController()
    cancel.current = controller
    const lock = await wakeLock()
    try {
      for (const episodeId of ids) {
        const job = bundle.jobs.find((j) => j.episodeId === episodeId) as JobInput
        await store.markRunning(bundle.batchId, episodeId)
        setBusy({ episodeId, phase: 'audio', fraction: 0 })
        const result = await exportEpisode(job, {
          staticBase: manifest.base,
          signal: controller.signal,
          onProgress: (phase, fraction) => setBusy({ episodeId, phase, fraction }),
        })
        await store.putExport({ batchId: bundle.batchId, episodeId, propsHash: job.propsHash, ...result, savedAt: new Date().toISOString() })
        await store.markRunning(bundle.batchId, null)
        await refresh(bundle)
      }
    } catch (e) {
      if (!(e instanceof DOMException && e.name === 'AbortError') && !controller.signal.aborted) setError(e)
      await store.markRunning(bundle.batchId, null)
      await refresh(bundle)
    } finally {
      setBusy(null)
      cancel.current = null
      await lock?.release().catch(() => undefined)
    }
  }

  const finalizeAndUpload = async () => {
    if (!bundle || !commit) return
    setConfirming(false)
    setUploadError(null)
    setUploading(true)
    try {
      const exports = await store.getExports(bundle.batchId)
      const byId = new Map(exports.map((e) => [e.episodeId, e]))
      const renders = bundle.jobs.map((job) => webRenderJson(bundle, job, (byId.get(job.episodeId) as NonNullable<ReturnType<typeof byId.get>>).files, commit))
      const body = packageWebBatch(bundle, renders, { createdAt: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'), commit })
      const response = await api.importBatch(body)
      let current = initialUploadState(response)
      setUploads(current)
      for (const row of current.rows.filter((r) => r.state !== 'present')) {
        const done = byId.get(row.expected.episodeId)
        const blob = row.expected.kind === 'video' ? done?.mp4 : done?.cover
        const name = row.expected.name
        if (!blob) {
          current = applyFailure(current, name, 'Not exported in this browser.')
          continue
        }
        current = markUploading(current, name)
        setUploads(current)
        try {
          const handle = api.uploadBatchFile(response.batchId, row.expected.kind, name, blob, (p) => {
            current = applyProgress(current, name, p.loaded, p.total)
            setUploads(current)
          })
          current = applyResult(current, name, await handle.promise)
        } catch (e) {
          current = applyFailure(current, name, describeError(e).message)
        }
        setUploads(current)
      }
    } catch (e) {
      setUploadError(e)
    } finally {
      setUploading(false)
    }
  }

  const left = remaining(rows)
  const ready = readyToPackage(rows)
  const summary = uploads ? uploadSummary(uploads) : null
  const totalBytes = rows.reduce((s, r) => s + (r.export?.files.video.bytes ?? 0) + (r.export?.files.cover.bytes ?? 0), 0)

  return (
    <>
      <section className="card stack" aria-labelledby={`${id}-open`}>
        <h2 id={`${id}-open`}>1. Open the job bundle</h2>
        <p>
          Choose <code>library/&lt;batchId&gt;/review/web-jobs.json</code> (Claude makes it with <code>web-jobs.mjs</code>). It may name answers: it stays in this
          browser and is never uploaded.
        </p>
        <div className="field">
          <label htmlFor={`${id}-file`}>Job bundle (web-jobs.json)</label>
          <input id={`${id}-file`} type="file" accept="application/json,.json" disabled={Boolean(busy) || uploading} onChange={(e) => e.target.files?.[0] && void open(e.target.files[0])} />
        </div>
        {problems.length ? (
          <div className="notice notice-error" role="alert">
            <p>This bundle cannot be used:</p>
            <ul>
              {problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {bundle ? (
          <p className="muted" data-testid="bundle-summary">
            Batch <code>{bundle.batchId}</code> · {bundle.jobs.length} episodes · made {bundle.createdAt.slice(0, 16).replace('T', ' ')} UTC from{' '}
            <code>{bundle.repoCommit.slice(0, 7)}</code>
            {store.durable ? '' : ' · this browser does not keep exports after a reload'}
          </p>
        ) : null}
      </section>

      <section className="card stack" aria-labelledby={`${id}-device`}>
        <h2 id={`${id}-device`}>2. This device</h2>
        {!device ? (
          <p className="muted">Checking what this browser can encode…</p>
        ) : device.canExport ? (
          <p>This browser can export H.264 + AAC at 1080 × 1920.</p>
        ) : (
          <div className="notice notice-error" role="alert">
            <p>This browser cannot export here:</p>
            <ul>
              {device.issues.map((i) => (
                <li key={i}>{i}</li>
              ))}
            </ul>
          </div>
        )}
        <p className={phone ? 'notice notice-warn' : 'hint'}>
          {phone
            ? 'On a phone: export one episode at a time, keep this tab open and the screen on. A laptop is better for whole batches.'
            : 'Keep this tab open and in front while exporting; finished episodes are kept, an interrupted one starts again.'}
        </p>
      </section>

      {bundle ? (
        <section className="card stack" aria-labelledby={`${id}-episodes`}>
          <h2 id={`${id}-episodes`}>3. Preview and export</h2>
          <div className="actions">
            <button type="button" className="btn btn-primary" disabled={!device?.canExport || Boolean(busy) || uploading || left.length === 0} onClick={() => void runExports(left)}>
              {left.length ? `Export ${left.length === rows.length ? 'all' : `the remaining ${left.length}`}` : 'All exported'}
            </button>
            {busy ? (
              <button type="button" className="btn" onClick={() => cancel.current?.abort()}>
                Cancel
              </button>
            ) : null}
          </div>
          <div role="status" aria-live="polite" data-testid="export-progress">
            {busy ? (
              <p>
                {busy.episodeId}: {PHASES[busy.phase]} {Math.round(busy.fraction * 100)}%
              </p>
            ) : null}
          </div>
          <ErrorNotice error={error} title="Export stopped" />
          <ul className="row-list">
            {rows.map((row) => (
              <li key={row.episodeId} className="stack" data-testid="export-row">
                <p className="row-head">
                  <strong>{row.episodeId}</strong>
                  <span className="muted">
                    {row.game} · {row.format}
                  </span>
                  <StatusBadge tone={statusTone(row)} label={STATUS_LABELS[row.status]} />
                </p>
                {row.export ? (
                  <p className="muted">
                    {formatBytes(row.export.files.video.bytes)} · {row.export.measures.loudnessLufs} LUFS · {row.export.measures.truePeakDbtp} dBTP · {row.export.seconds} s to export
                  </p>
                ) : null}
                {row.export?.errors.length ? (
                  <ul className="field-issues">
                    {row.export.errors.map((e) => (
                      <li key={e}>{e}</li>
                    ))}
                  </ul>
                ) : null}
                <div className="actions">
                  <button type="button" className="btn btn-quiet" aria-expanded={preview === row.episodeId} onClick={() => setPreview(preview === row.episodeId ? null : row.episodeId)}>
                    {preview === row.episodeId ? 'Close preview' : 'Preview'}
                  </button>
                  <button type="button" className="btn" disabled={!device?.canExport || Boolean(busy) || uploading} onClick={() => void runExports([row.episodeId])}>
                    {row.export ? 'Export again' : 'Export'}
                  </button>
                  {row.export ? (
                    <button type="button" className="btn btn-quiet" onClick={() => row.export && saveBlob(`${row.episodeId}.mp4`, row.export.mp4)}>
                      Save video
                    </button>
                  ) : null}
                </div>
                {preview === row.episodeId ? <EpisodePreview staticBase={manifest.base} job={bundle.jobs.find((j) => j.episodeId === row.episodeId) as JobInput} /> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {bundle ? (
        <section className="card stack" aria-labelledby={`${id}-upload`}>
          <h2 id={`${id}-upload`}>4. Finalize and upload</h2>
          <p>
            When every episode passed its checks, finalize the batch: it is packaged here (batch.json, with the same code as the Mac) and uploaded with its videos and
            covers; the Pi validates everything again. Review and approve the episodes in the Library afterwards.
          </p>
          {!commit ? <p className="muted">Waiting for this Pi's version (Settings › Update)…</p> : null}
          <div className="actions">
            <button type="button" className="btn" disabled={!ready || !commit || uploading || Boolean(busy)} onClick={() => setConfirming(true)}>
              Finalize and upload {bundle.batchId}
            </button>
          </div>
          {!ready ? <p className="hint">Available once every episode shows “Passed checks”.</p> : <p className="hint">{formatBytes(totalBytes)} to upload.</p>}
          <ErrorNotice error={uploadError} title="Upload failed" />
          {uploads && summary ? (
            <div role="status" aria-live="polite" className="stack" data-testid="upload-status">
              <p>
                {summary.present} of {summary.total} files on the Pi{summary.complete ? ' — complete. Review the episodes in the Library.' : '.'}
              </p>
              {summary.complete ? (
                <p>
                  <a href="#/library">Open the Library →</a>
                </p>
              ) : null}
              <ul className="compact-list">
                {uploads.rows
                  .filter((r) => r.state !== 'present')
                  .map((r) => (
                    <li key={r.expected.name}>
                      {r.expected.name}: {r.message ?? r.state}
                    </li>
                  ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}

      {confirming && bundle ? (
        <ConfirmDialog title={`Finalize and upload ${bundle.batchId}?`} confirmLabel="Finalize and upload" onConfirm={() => void finalizeAndUpload()} onCancel={() => setConfirming(false)}>
          <p>
            This is your approval to finalize this batch: its batch.json is written now and frozen, and {rows.length} videos and covers go to the Pi. A correction later
            needs a new revision or a new batch.
          </p>
        </ConfirmDialog>
      ) : null}
    </>
  )
}

/** Remotion Player preview of one job, with the Pi's assets. */
function EpisodePreview({ staticBase, job }: { staticBase: string; job: JobInput }) {
  const [component, setComponent] = useState<ComponentType<Record<string, unknown>> | null>(null)
  const [error, setError] = useState<unknown>(null)
  useEffect(() => {
    let live = true
    loadKit(staticBase).then(
      (kit) => live && setComponent(() => kit.LibraryEpisode as unknown as ComponentType<Record<string, unknown>>),
      (e: unknown) => live && setError(e),
    )
    return () => {
      live = false
    }
  }, [staticBase])
  if (error) return <ErrorNotice error={error} title="Preview unavailable" />
  if (!component) return <Loading />
  return (
    <div className="motion-preview">
      <Player
        component={component}
        inputProps={job.props as unknown as Record<string, unknown>}
        durationInFrames={job.props.durationInFrames}
        compositionWidth={WIDTH}
        compositionHeight={HEIGHT}
        fps={FPS}
        controls
        acknowledgeRemotionLicense
        className="motion-player"
      />
    </div>
  )
}
