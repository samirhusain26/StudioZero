/**
 * Pure state for the "Add batch" upload flow (L12): batch.json first, then each
 * video/cover file in its own request, matched by name to the expected list and
 * verified by sha256/size on the Pi.
 */
import type { BatchImportResponse, ExpectedFile, FileUploadResult } from '../api/types'
import { formatBytes } from './format'

export type UploadRowState =
  | 'present' // verified bytes on the Pi (before or after this session)
  | 'missing' // not on the Pi (never uploaded, or interrupted)
  | 'queued'
  | 'uploading'
  | 'size-mismatch' // local size differs from batch.json; not uploaded
  | 'mismatch' // the Pi computed a different sha256/size; not stored

export interface UploadRow {
  expected: ExpectedFile
  state: UploadRowState
  loaded: number
  total: number
  /** Plain status text shown next to the row (never colour alone). */
  message: string | null
  result: FileUploadResult | null
}

export interface UploadState {
  batchId: string
  rows: UploadRow[]
  /** Selected files that batch.json does not list. */
  unexpected: { name: string; reason: string }[]
  /** Selected files skipped because the Pi already has them. */
  skipped: string[]
}

export interface SelectedFile {
  name: string
  size: number
}

export const ROW_LABELS: Record<UploadRowState, string> = {
  present: 'On the Pi (verified)',
  missing: 'Missing',
  queued: 'Queued',
  uploading: 'Uploading',
  'size-mismatch': 'Size differs — not uploaded',
  mismatch: 'Hash mismatch — not stored',
}

export function initialUploadState(response: BatchImportResponse): UploadState {
  return {
    batchId: response.batchId,
    rows: response.expected.map((expected) => ({
      expected,
      state: expected.present ? 'present' : 'missing',
      loaded: expected.present ? expected.bytes : 0,
      total: expected.bytes,
      message: expected.present ? 'Already on the Pi' : null,
      result: null,
    })),
    unexpected: [],
    skipped: [],
  }
}

function kindFor(name: string): 'video' | 'cover' | null {
  const lower = name.toLowerCase()
  if (lower.endsWith('.mp4')) return 'video'
  if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'cover'
  return null
}

/**
 * Match selected files to expected rows. Returns the new state and the names
 * to upload (in expected order). Files already on the Pi are skipped.
 */
export function matchSelection(state: UploadState, files: readonly SelectedFile[]): { state: UploadState; toUpload: string[] } {
  const rows = state.rows.map((row) => ({ ...row }))
  const unexpected: UploadState['unexpected'] = []
  const skipped: string[] = []
  const queued = new Set<string>()
  for (const file of files) {
    const kind = kindFor(file.name)
    const row = rows.find((r) => r.expected.name === file.name && (kind === null || r.expected.kind === kind))
    if (!row) {
      unexpected.push({
        name: file.name,
        reason: kind ? 'Not listed in batch.json; not uploaded' : 'Only .mp4 videos and .jpg covers are uploaded',
      })
      continue
    }
    if (row.state === 'present') {
      skipped.push(file.name)
      continue
    }
    if (row.state === 'uploading' || row.state === 'queued') continue
    if (file.size !== row.expected.bytes) {
      row.state = 'size-mismatch'
      row.message = `Selected file is ${formatBytes(file.size)}; batch.json says ${formatBytes(row.expected.bytes)}. Choose the file from this batch folder.`
      continue
    }
    row.state = 'queued'
    row.loaded = 0
    row.message = null
    queued.add(file.name)
  }
  const toUpload = rows.filter((r) => queued.has(r.expected.name)).map((r) => r.expected.name)
  return { state: { ...state, rows, unexpected, skipped }, toUpload }
}

function update(state: UploadState, name: string, change: (row: UploadRow) => UploadRow): UploadState {
  return { ...state, rows: state.rows.map((row) => (row.expected.name === name ? change(row) : row)) }
}

export function markUploading(state: UploadState, name: string): UploadState {
  return update(state, name, (row) => ({ ...row, state: 'uploading', loaded: 0, message: null }))
}

export function applyProgress(state: UploadState, name: string, loaded: number, total: number): UploadState {
  return update(state, name, (row) => ({ ...row, loaded, total: total || row.total }))
}

export function applyResult(state: UploadState, name: string, result: FileUploadResult): UploadState {
  return update(state, name, (row) => {
    if (result.matched && result.outcome !== 'rejected') {
      return {
        ...row,
        state: 'present',
        loaded: row.expected.bytes,
        result,
        message: result.outcome === 'already-present' ? 'Already on the Pi (same hash)' : 'Uploaded; sha256 and size match',
      }
    }
    const why = result.sha256 !== result.expectedSha256
      ? `sha256 ${result.sha256.slice(0, 8)} ≠ expected ${result.expectedSha256.slice(0, 8)}`
      : result.bytes !== result.expectedBytes
        ? `size ${formatBytes(result.bytes)} ≠ expected ${formatBytes(result.expectedBytes)}`
        : 'rejected by the Pi'
    return { ...row, state: 'mismatch', result, loaded: 0, message: `${why}${result.message ? `: ${result.message}` : ''}` }
  })
}

/** Interrupted or failed uploads show as missing and can be re-selected. */
export function applyFailure(state: UploadState, name: string, message: string): UploadState {
  return update(state, name, (row) => ({ ...row, state: 'missing', loaded: 0, message: `${message} Select the file again to retry.` }))
}

export interface UploadCounts {
  total: number
  /** Verified on the Pi (uploaded now or before). */
  verified: number
  /** Already on the Pi when the batch was imported (skipped, never sent). */
  alreadyOnPi: number
  uploading: number
  queued: number
  /** Tried and failed (interrupted, hash or size mismatch); can be retried. */
  failed: number
  /** Not on the Pi and not tried yet in this session. */
  waiting: number
  totalBytes: number
  /** Verified bytes plus bytes sent for the file in progress. */
  doneBytes: number
}

/** Per-state counts and bytes for the upload progress summary. */
export function uploadCounts(state: UploadState): UploadCounts {
  const counts: UploadCounts = { total: state.rows.length, verified: 0, alreadyOnPi: 0, uploading: 0, queued: 0, failed: 0, waiting: 0, totalBytes: 0, doneBytes: 0 }
  for (const row of state.rows) {
    counts.totalBytes += row.expected.bytes
    if (row.expected.present) counts.alreadyOnPi++
    switch (row.state) {
      case 'present':
        counts.verified++
        counts.doneBytes += row.expected.bytes
        break
      case 'uploading':
        counts.uploading++
        counts.doneBytes += Math.min(row.loaded, row.expected.bytes)
        break
      case 'queued':
        counts.queued++
        break
      case 'mismatch':
      case 'size-mismatch':
        counts.failed++
        break
      case 'missing':
        if (row.message) counts.failed++
        else counts.waiting++
        break
    }
  }
  return counts
}

export function uploadSummary(state: UploadState): { total: number; present: number; missing: number; complete: boolean } {
  const total = state.rows.length
  const present = state.rows.filter((r) => r.state === 'present').length
  return { total, present, missing: total - present, complete: total > 0 && present === total }
}
