import { describe, expect, it } from 'vitest'
import type { BatchImportResponse, ExpectedFile, FileUploadResult } from '../api/types'
import { applyFailure, applyProgress, applyResult, initialUploadState, markUploading, matchSelection, uploadCounts, uploadSummary } from './uploadPlan'

const sha = (c: string) => c.repeat(64)
function expected(name: string, kind: 'video' | 'cover', bytes: number, present = false): ExpectedFile {
  return {
    file: `${kind === 'video' ? 'videos' : 'covers'}/${name}`,
    name,
    kind,
    episodeId: name.replace(/\.(mp4|jpg)$/, ''),
    revision: 1,
    sha256: sha(kind === 'video' ? 'a' : 'b'),
    bytes,
    present,
  }
}

const response: BatchImportResponse = {
  batchId: '2026-10-pilots',
  origin: 'mac',
  created: true,
  merge: [],
  problems: [],
  warnings: [],
  expected: [
    expected('scalar-clues-001.mp4', 'video', 1000),
    expected('scalar-clues-001.jpg', 'cover', 100, true),
    expected('scalar-clues-002.mp4', 'video', 2000),
  ],
}

function result(overrides: Partial<FileUploadResult>): FileUploadResult {
  return {
    file: 'videos/scalar-clues-001.mp4',
    kind: 'video',
    episodeId: 'scalar-clues-001',
    sha256: sha('a'),
    bytes: 1000,
    expectedSha256: sha('a'),
    expectedBytes: 1000,
    matched: true,
    outcome: 'stored',
    message: null,
    problems: [],
    episodeStatus: 'reviewable',
    ...overrides,
  }
}

describe('upload matching', () => {
  it('starts from present/missing', () => {
    const state = initialUploadState(response)
    expect(state.rows.map((r) => r.state)).toEqual(['missing', 'present', 'missing'])
    expect(uploadSummary(state)).toEqual({ total: 3, present: 1, missing: 2, complete: false })
  })

  it('skips files already on the Pi and rejects unexpected or wrong-size files', () => {
    const { state, toUpload } = matchSelection(initialUploadState(response), [
      { name: 'scalar-clues-001.mp4', size: 1000 },
      { name: 'scalar-clues-001.jpg', size: 100 },
      { name: 'scalar-clues-002.mp4', size: 1999 },
      { name: 'other.mp4', size: 5 },
      { name: 'notes.txt', size: 5 },
    ])
    expect(toUpload).toEqual(['scalar-clues-001.mp4'])
    expect(state.skipped).toEqual(['scalar-clues-001.jpg'])
    expect(state.rows[0]?.state).toBe('queued')
    expect(state.rows[2]?.state).toBe('size-mismatch')
    expect(state.unexpected.map((u) => u.name)).toEqual(['other.mp4', 'notes.txt'])
  })

  it('tracks progress, verified results and hash mismatches', () => {
    let { state } = matchSelection(initialUploadState(response), [{ name: 'scalar-clues-001.mp4', size: 1000 }])
    state = markUploading(state, 'scalar-clues-001.mp4')
    state = applyProgress(state, 'scalar-clues-001.mp4', 400, 1000)
    expect(state.rows[0]).toMatchObject({ state: 'uploading', loaded: 400, total: 1000 })
    const verified = applyResult(state, 'scalar-clues-001.mp4', result({}))
    expect(verified.rows[0]).toMatchObject({ state: 'present', message: 'Uploaded; sha256 and size match' })
    const mismatch = applyResult(state, 'scalar-clues-001.mp4', result({ matched: false, outcome: 'rejected', sha256: sha('c') }))
    expect(mismatch.rows[0]?.state).toBe('mismatch')
    expect(mismatch.rows[0]?.message).toContain('sha256 cccccccc ≠ expected aaaaaaaa')
  })

  it('shows interrupted uploads as missing so they can be re-selected', () => {
    let { state } = matchSelection(initialUploadState(response), [{ name: 'scalar-clues-001.mp4', size: 1000 }])
    state = markUploading(state, 'scalar-clues-001.mp4')
    state = applyFailure(state, 'scalar-clues-001.mp4', 'Upload interrupted.')
    expect(state.rows[0]).toMatchObject({ state: 'missing', loaded: 0 })
    expect(state.rows[0]?.message).toBe('Upload interrupted. Select the file again to retry.')
    const again = matchSelection(state, [{ name: 'scalar-clues-001.mp4', size: 1000 }])
    expect(again.toUpload).toEqual(['scalar-clues-001.mp4'])
  })

  it('completes when every expected file is present', () => {
    let state = initialUploadState(response)
    state = applyResult(state, 'scalar-clues-001.mp4', result({}))
    state = applyResult(state, 'scalar-clues-002.mp4', result({ file: 'videos/scalar-clues-002.mp4', bytes: 2000, expectedBytes: 2000, outcome: 'already-present' }))
    expect(uploadSummary(state).complete).toBe(true)
  })
})

describe('uploadCounts', () => {
  it('counts verified, uploading, queued, failed, skipped-already-on-Pi and bytes', () => {
    let state = initialUploadState(response)
    expect(uploadCounts(state)).toMatchObject({ total: 3, verified: 1, alreadyOnPi: 1, waiting: 2, failed: 0, totalBytes: 3100, doneBytes: 100 })
    state = matchSelection(state, [
      { name: 'scalar-clues-001.mp4', size: 1000 },
      { name: 'scalar-clues-002.mp4', size: 2000 },
    ]).state
    expect(uploadCounts(state)).toMatchObject({ queued: 2, waiting: 0 })
    state = applyProgress(markUploading(state, 'scalar-clues-001.mp4'), 'scalar-clues-001.mp4', 400, 1000)
    expect(uploadCounts(state)).toMatchObject({ uploading: 1, queued: 1, doneBytes: 500 })
    state = applyFailure(state, 'scalar-clues-001.mp4', 'Upload interrupted.')
    state = applyResult(
      markUploading(state, 'scalar-clues-002.mp4'),
      'scalar-clues-002.mp4',
      result({ file: 'videos/scalar-clues-002.mp4', bytes: 2000, expectedBytes: 2000 }),
    )
    expect(uploadCounts(state)).toMatchObject({ verified: 2, failed: 1, uploading: 0, queued: 0, waiting: 0, doneBytes: 2100 })
  })
})
