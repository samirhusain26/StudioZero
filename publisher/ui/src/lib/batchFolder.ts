/**
 * Pure helpers for "choose the batch folder" (Add batch): find library/<batchId>/ in a
 * folder selection, require the finalize marker, and pick exactly the files batch.json
 * lists. Everything else in the folder (review/, masters, frames) is never uploaded.
 */
import type { ExpectedFile } from '../api/types'

export interface FolderFile {
  /** Path relative to the chosen folder's parent, as the browser reports it (webkitRelativePath). */
  path: string
  size: number
}

export interface BatchFolder {
  /** Folder prefix ending in "/", e.g. "2026-10-b01/" or "library/2026-10-b01/". */
  root: string
  batchJson: string
  ready: string
  /** Files outside the batch's own batch.json / READY_FOR_UPLOAD / videos/ / covers/ (never uploaded). */
  ignored: number
}

const BATCH_JSON = 'batch.json'
const READY = 'READY_FOR_UPLOAD'

const dirOf = (path: string) => path.slice(0, path.lastIndexOf('/') + 1)

/** Locate the one finalized batch in a folder selection, or explain what to choose instead. */
export function findBatchFolder(files: readonly FolderFile[]): BatchFolder | string {
  const paths = new Set(files.map((f) => f.path))
  // A batch root is a folder holding batch.json directly; review/ never holds one.
  const roots = [...paths].filter((p) => p.endsWith(`/${BATCH_JSON}`) || p === BATCH_JSON).map(dirOf)
  const [root, ...others] = roots
  if (root === undefined) return 'No batch.json in this folder. Choose the batch folder itself: library/<batchId>/.'
  if (others.length > 0) {
    const names = roots.map((r) => r.replace(/\/$/, '').split('/').pop()).join(', ')
    return `This folder holds ${roots.length} batches (${names}). Choose one batch folder.`
  }
  if (!paths.has(`${root}${READY}`)) return 'This batch is not finalized (no READY_FOR_UPLOAD). Run finalize on the Mac first.'
  const own = (p: string) => p === `${root}${BATCH_JSON}` || p === `${root}${READY}` || /^(videos|covers)\/[^/]+$/.test(p.slice(root.length))
  const ignored = files.filter((f) => !f.path.startsWith(root) || !own(f.path)).length
  return { root, batchJson: `${root}${BATCH_JSON}`, ready: `${root}${READY}`, ignored }
}

/** READY_FOR_UPLOAD must record the sha256 of this exact batch.json (finalize writes it). */
export function checkReadyMarker(markerText: string, batchJsonSha256: string): string | null {
  let marker: { batchJsonSha256?: unknown }
  try {
    marker = JSON.parse(markerText) as { batchJsonSha256?: unknown }
  } catch {
    return 'READY_FOR_UPLOAD is not valid JSON. Run finalize again.'
  }
  if (typeof marker.batchJsonSha256 !== 'string') return 'READY_FOR_UPLOAD has no batchJsonSha256. Run finalize again.'
  if (marker.batchJsonSha256 !== batchJsonSha256) return 'batch.json changed after finalize. Run finalize again before uploading.'
  return null
}

/** Folder files that are exactly the expected videos/covers (matched by path inside the batch folder). */
export function expectedFilesIn<F extends FolderFile>(files: readonly F[], root: string, expected: readonly ExpectedFile[]): F[] {
  const wanted = new Set(expected.map((e) => `${root}${e.file}`))
  return files.filter((f) => wanted.has(f.path))
}
