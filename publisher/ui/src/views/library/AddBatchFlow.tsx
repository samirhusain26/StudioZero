import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { api } from '../../api/client'
import type { BatchImportResponse } from '../../api/types'
import { describeError, ErrorNotice } from '../../components/ErrorNotice'
import { StatusBadge } from '../../components/StatusBadge'
import { checkReadyMarker, expectedFilesIn, findBatchFolder } from '../../lib/batchFolder'
import { MAX_BATCH_JSON_BYTES } from '../../lib/contract'
import { filesFromEntries, type EntryLike, type PathFile } from '../../lib/dropFolder'
import { formatBytes, shortHash } from '../../lib/format'
import type { Tone } from '../../lib/labels'
import {
  applyFailure,
  applyProgress,
  applyResult,
  initialUploadState,
  markUploading,
  matchSelection,
  ROW_LABELS,
  uploadCounts,
  uploadSummary,
  type UploadRowState,
  type UploadState,
} from '../../lib/uploadPlan'

const ROW_TONE: Record<UploadRowState, Tone> = {
  present: 'good',
  missing: 'warn',
  queued: 'neutral',
  uploading: 'info',
  'size-mismatch': 'bad',
  mismatch: 'bad',
}

interface ChosenBatch {
  text: string
  batchId: string
  episodes: number
  bytes: number
}

interface ChosenFolder extends ChosenBatch {
  root: string
  ignored: number
}

/** A folder dropped on the Library page (entries taken during the drop event). */
export interface DroppedFolder {
  entries: EntryLike[]
  nonce: number
}

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text))
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

/** Read a folder selection: the one finalized batch in it, with batch.json matching its READY_FOR_UPLOAD. */
async function readBatchFolder(files: PathFile[]): Promise<{ folder: ChosenFolder; files: PathFile[] } | string> {
  const found = findBatchFolder(files)
  if (typeof found === 'string') return found
  const byPath = new Map(files.map((f) => [f.path, f.file]))
  const batchFile = byPath.get(found.batchJson)
  const readyFile = byPath.get(found.ready)
  if (!batchFile || !readyFile) return 'batch.json or READY_FOR_UPLOAD could not be read from this folder.'
  const parsed = parseBatchFile(await batchFile.text(), batchFile.size)
  if (typeof parsed === 'string') return parsed
  if (!globalThis.crypto?.subtle) return 'This page cannot check READY_FOR_UPLOAD here (it needs the HTTPS address).'
  const stale = checkReadyMarker(await readyFile.text(), await sha256Hex(parsed.text))
  if (stale) return stale
  return { folder: { ...parsed, root: found.root, ignored: found.ignored }, files }
}

export function parseBatchFile(text: string, bytes: number): ChosenBatch | string {
  if (bytes > MAX_BATCH_JSON_BYTES) return 'batch.json is larger than 1 MB.'
  try {
    const data = JSON.parse(text) as { batchId?: unknown; episodes?: unknown }
    if (typeof data.batchId !== 'string' || !Array.isArray(data.episodes)) return 'This file does not look like a batch.json (batchId and episodes are missing).'
    return { text, batchId: data.batchId, episodes: data.episodes.length, bytes }
  } catch {
    return 'batch.json is not valid JSON.'
  }
}

export function AddBatchFlow({
  onDone,
  dropped = null,
  heading = 'Upload a batch',
  bare = false,
}: {
  onDone: () => void
  dropped?: DroppedFolder | null
  /** null: no heading (the surrounding step names it). */
  heading?: string | null
  /** Inside another card: no card of its own. */
  bare?: boolean
}) {
  const [chosen, setChosen] = useState<ChosenFolder | null>(null)
  const [chooseError, setChooseError] = useState<string | null>(null)
  const [imported, setImported] = useState<BatchImportResponse | null>(null)
  const [uploads, setUploads] = useState<UploadState | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const files = useRef(new Map<string, File>())
  const folderFiles = useRef<PathFile[]>([])
  const busyRef = useRef(false)
  useEffect(() => {
    busyRef.current = busy
  })

  const loadFolder = async (selected: PathFile[]) => {
    setChooseError(null)
    setError(null)
    setImported(null)
    setUploads(null)
    setChosen(null)
    files.current.clear()
    folderFiles.current = []
    if (selected.length === 0) return
    const read = await readBatchFolder(selected)
    if (typeof read === 'string') {
      setChooseError(read)
      return
    }
    folderFiles.current = read.files
    setChosen(read.folder)
  }

  const chooseFolder = async (event: ChangeEvent<HTMLInputElement>) => {
    const selected = [...(event.target.files ?? [])].map((file) => ({ file, path: file.webkitRelativePath || file.name, size: file.size }))
    event.target.value = ''
    await loadFolder(selected)
  }

  // A folder dropped anywhere on the Library page (LibraryView captures the entries).
  const loadRef = useRef(loadFolder)
  useEffect(() => {
    loadRef.current = loadFolder
  })
  useEffect(() => {
    if (!dropped || busyRef.current) return
    let cancelled = false
    void filesFromEntries(dropped.entries).then(
      (list) => {
        if (!cancelled) void loadRef.current(list)
      },
      () => {
        if (!cancelled) setChooseError('The dropped folder could not be read. Choose it with the folder picker instead.')
      },
    )
    return () => {
      cancelled = true
    }
  }, [dropped])

  /** Send batch.json, then upload every listed video and cover from the chosen folder. */
  const uploadBatch = async () => {
    if (!chosen) return
    setBusy(true)
    setError(null)
    let response: BatchImportResponse
    try {
      response = await api.importBatch(chosen.text)
    } catch (e) {
      setError(e)
      setBusy(false)
      return
    }
    setImported(response)
    if (response.problems.length > 0) {
      setBusy(false)
      return
    }
    await uploadFiles(initialUploadState(response), expectedFilesIn(folderFiles.current, chosen.root, response.expected).map((f) => f.file))
  }

  const retryMissing = async () => {
    if (!uploads || !chosen) return
    const missing = uploads.rows.filter((r) => r.state === 'missing').map((r) => r.expected)
    await uploadFiles(uploads, expectedFilesIn(folderFiles.current, chosen.root, missing).map((f) => f.file))
  }

  const uploadFiles = async (start: UploadState, selected: File[]) => {
    for (const file of selected) files.current.set(file.name, file)
    const { state, toUpload } = matchSelection(start, selected)
    setUploads(state)
    if (toUpload.length === 0) {
      setBusy(false)
      return
    }
    setBusy(true)
    let current = state
    // One request per file, sequentially (keeps the Pi's memory and disk I/O steady).
    for (const name of toUpload) {
      const file = files.current.get(name)
      const row = current.rows.find((r) => r.expected.name === name)
      if (!file || !row) continue
      current = markUploading(current, name)
      setUploads(current)
      try {
        const handle = api.uploadBatchFile(current.batchId, row.expected.kind, name, file, (p) => {
          current = applyProgress(current, name, p.loaded, p.total)
          setUploads(current)
        })
        const result = await handle.promise
        current = applyResult(current, name, result)
      } catch (e) {
        current = applyFailure(current, name, describeError(e).message)
      }
      setUploads(current)
    }
    setBusy(false)
  }

  const summary = uploads ? uploadSummary(uploads) : null
  const counts = uploads ? uploadCounts(uploads) : null
  return (
    <section className={bare ? 'stack' : 'card stack'} aria-labelledby={heading ? 'add-batch-h' : undefined} aria-label={heading ? undefined : 'Upload a batch'}>
      {heading ? <h2 id="add-batch-h">{heading}</h2> : null}
      {busy ? null : (
        <div className="drop-zone" data-testid="drop-zone">
          <div className="field">
            <label htmlFor="batch-folder">Batch folder</label>
            <input id="batch-folder" type="file" multiple {...{ webkitdirectory: '' }} onChange={chooseFolder} disabled={busy} />
          </div>
          <p className="hint">
            Drop the finalized <code>library/&lt;batchId&gt;/</code> folder anywhere on the Library page, or choose it. Only <code>batch.json</code>{' '}
            and the listed videos and covers are sent, each checked by sha256; <code>review/</code> stays on the Mac.
          </p>
        </div>
      )}
      {chooseError ? (
        <p className="notice notice-error" role="alert">
          {chooseError}
        </p>
      ) : null}
      {chosen ? (
        <div className="stack">
          <p>
            Batch <strong>{chosen.batchId}</strong>: {chosen.episodes} episode{chosen.episodes === 1 ? '' : 's'}, finalized.
            {chosen.ignored ? ` ${chosen.ignored} other file${chosen.ignored === 1 ? '' : 's'} in the folder (review/ etc.) will not be uploaded.` : ''}
          </p>
          {!imported ? (
            <div className="actions">
              <button type="button" className="btn btn-primary" onClick={uploadBatch} disabled={busy}>
                {busy ? 'Sending…' : 'Upload batch'}
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
      <ErrorNotice error={error} title="Import failed" />

      {imported ? (
        <div className="stack" aria-live="polite">
          <h3>
            Batch {imported.batchId} {imported.created ? 'imported' : 'already known (merge)'}
          </h3>
          {imported.problems.length ? (
            <div className="notice notice-error" role="alert">
              <p>
                <strong>The Pi rejected this batch.json.</strong> Fix these on the Mac, run finalize again, then choose the folder again.
              </p>
              <ul className="problem-list">
                {imported.problems.map((p, i) => (
                  <li key={`${p.path}-${i}`}>
                    {p.message} <code className="muted">{p.path}</code>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {imported.warnings.length ? (
            <ul className="problem-list">
              {imported.warnings.map((w, i) => (
                <li key={`${w.path}-${i}`}>Warning: {w.message}</li>
              ))}
            </ul>
          ) : null}
          {imported.merge.length ? (
            <ul className="compact-list">
              {imported.merge.map((m) => (
                <li key={`${m.episodeId}@${m.revision}`}>
                  {m.episodeId} rev {m.revision}: {m.outcome.replace(/-/g, ' ')}
                  {m.message ? ` — ${m.message}` : ''}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {uploads && summary && counts ? (
        <div className="stack">
          <h3>Expected files</h3>
          <p role="status" aria-live="polite">
            {summary.present} of {summary.total} files on the Pi; {summary.missing} missing.
            {summary.complete ? ' All files verified.' : ''}
          </p>
          <ul className="upload-counts" data-testid="upload-counts">
            <li>
              <strong>{counts.verified}</strong> verified
            </li>
            <li>
              <strong>{counts.uploading}</strong> uploading
            </li>
            <li>
              <strong>{counts.queued}</strong> queued
            </li>
            <li>
              <strong>{counts.failed}</strong> failed
            </li>
            <li>
              <strong>{counts.alreadyOnPi}</strong> skipped (already on the Pi)
            </li>
            {counts.waiting ? (
              <li>
                <strong>{counts.waiting}</strong> not sent yet
              </li>
            ) : null}
            <li>
              {formatBytes(counts.doneBytes)} of {formatBytes(counts.totalBytes)}
            </li>
          </ul>
          {counts.totalBytes > 0 ? (
            <progress max={counts.totalBytes} value={counts.doneBytes} aria-label="Batch upload progress">
              {Math.round((counts.doneBytes / counts.totalBytes) * 100)}%
            </progress>
          ) : null}
          {summary.missing > 0 && !busy ? (
            <div className="actions">
              <button type="button" className="btn btn-primary" onClick={retryMissing}>
                Retry missing files
              </button>
            </div>
          ) : null}
          <p className="hint">Files already on the Pi are skipped. If the page was closed mid-upload, choose the folder again.</p>
          {uploads.skipped.length ? <p className="muted">Skipped (already on the Pi): {uploads.skipped.join(', ')}</p> : null}
          {uploads.unexpected.length ? (
            <ul className="problem-list">
              {uploads.unexpected.map((u) => (
                <li key={u.name}>
                  {u.name}: {u.reason}
                </li>
              ))}
            </ul>
          ) : null}
          <details className="disclosure">
            <summary>Files ({uploads.rows.length})</summary>
          <ul className="upload-list">
            {uploads.rows.map((row) => (
              <li key={row.expected.file} className="upload-row">
                <p className="row-head">
                  <code>{row.expected.file}</code> <StatusBadge tone={ROW_TONE[row.state]} label={ROW_LABELS[row.state]} />
                </p>
                <p className="muted">
                  {formatBytes(row.expected.bytes)} · sha256 <code>{shortHash(row.expected.sha256, 12)}</code>
                </p>
                {row.state === 'uploading' ? (
                  <progress max={row.total || row.expected.bytes} value={row.loaded} aria-label={`Upload progress for ${row.expected.name}`}>
                    {Math.round((row.loaded / (row.total || 1)) * 100)}%
                  </progress>
                ) : null}
                {row.message ? <p>{row.message}</p> : null}
              </li>
            ))}
          </ul>
          </details>
          <div className="actions">
            <button type="button" className="btn" onClick={onDone} disabled={busy}>
              {summary.complete ? 'Done — review in the library' : 'Back to the library (finish later)'}
            </button>
          </div>
        </div>
      ) : null}
    </section>
  )
}
