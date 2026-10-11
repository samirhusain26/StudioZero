import { createHash } from 'node:crypto'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BatchImportResponse, ExpectedFile, FileUploadResult } from '../../api/types'
import { AddBatchFlow } from './AddBatchFlow'

const { api } = vi.hoisted(() => ({ api: { importBatch: vi.fn(), uploadBatchFile: vi.fn() } }))
vi.mock('../../api/client', async (importOriginal) => ({ ...(await importOriginal<typeof import('../../api/client')>()), api }))

const batchJson = JSON.stringify({ schemaVersion: 1, batchId: '2026-10-b01', episodes: [{}] })
const sha = (s: string) => createHash('sha256').update(s).digest('hex')

function inFolder(path: string, body: BlobPart, type = ''): File {
  const file = new File([body], path.split('/').pop() ?? path, { type })
  Object.defineProperty(file, 'webkitRelativePath', { value: path })
  return file
}
function folder(marker = JSON.stringify({ schemaVersion: 1, batchJsonSha256: sha(batchJson) })): File[] {
  return [
    inFolder('2026-10-b01/batch.json', batchJson),
    inFolder('2026-10-b01/READY_FOR_UPLOAD', marker),
    inFolder('2026-10-b01/videos/scalar-clues-002.mp4', new Uint8Array(new ArrayBuffer(1000))),
    inFolder('2026-10-b01/covers/scalar-clues-002.jpg', new Uint8Array(new ArrayBuffer(100))),
    inFolder('2026-10-b01/review/index.html', '<html>'),
    inFolder('2026-10-b01/review/jobs/scalar-clues-002/scalar-clues-002.mp4', new Uint8Array(new ArrayBuffer(1000))),
  ]
}
function expected(file: string, kind: 'video' | 'cover', bytes: number): ExpectedFile {
  return { file, name: file.split('/')[1] ?? file, kind, episodeId: 'scalar-clues-002', revision: 1, sha256: 'a'.repeat(64), bytes, present: false }
}
const response: BatchImportResponse = {
  batchId: '2026-10-b01', origin: 'mac', created: true, merge: [], problems: [], warnings: [],
  expected: [expected('videos/scalar-clues-002.mp4', 'video', 1000), expected('covers/scalar-clues-002.jpg', 'cover', 100)],
}
const stored = (name: string, kind: 'video' | 'cover', bytes: number): FileUploadResult => ({
  file: `${kind === 'video' ? 'videos' : 'covers'}/${name}`, kind, episodeId: 'scalar-clues-002', sha256: 'a'.repeat(64), bytes,
  expectedSha256: 'a'.repeat(64), expectedBytes: bytes, matched: true, outcome: 'stored', message: null, problems: [], episodeStatus: 'reviewable',
})

const choose = (files: File[]) => fireEvent.change(screen.getByLabelText('Batch folder'), { target: { files } })

describe('AddBatchFlow folder upload', () => {
  beforeEach(() => {
    api.importBatch.mockReset().mockResolvedValue(response)
    api.uploadBatchFile.mockReset().mockImplementation((_b: string, kind: 'video' | 'cover', name: string, file: Blob) => ({
      promise: Promise.resolve(stored(name, kind, file.size)),
    }))
  })

  it('one folder pick + Upload sends batch.json and only the listed videos and covers', async () => {
    render(<AddBatchFlow onDone={vi.fn()} />)
    choose(folder())
    expect(await screen.findByText(/finalized\./)).toHaveTextContent('Batch 2026-10-b01: 1 episode, finalized. 2 other files in the folder (review/ etc.) will not be uploaded.')
    await userEvent.setup().click(screen.getByRole('button', { name: 'Upload batch' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('2 of 2 files on the Pi; 0 missing. All files verified.'))
    expect(api.importBatch).toHaveBeenCalledWith(batchJson)
    expect(api.uploadBatchFile.mock.calls.map((c) => [c[1], c[2], (c[3] as File).webkitRelativePath])).toEqual([
      ['video', 'scalar-clues-002.mp4', '2026-10-b01/videos/scalar-clues-002.mp4'],
      ['cover', 'scalar-clues-002.jpg', '2026-10-b01/covers/scalar-clues-002.jpg'],
    ])
  })

  it('refuses a folder whose batch.json changed after finalize', async () => {
    render(<AddBatchFlow onDone={vi.fn()} />)
    choose(folder(JSON.stringify({ batchJsonSha256: 'c'.repeat(64) })))
    expect(await screen.findByRole('alert')).toHaveTextContent('batch.json changed after finalize')
    expect(screen.queryByRole('button', { name: 'Upload batch' })).toBeNull()
    expect(api.importBatch).not.toHaveBeenCalled()
  })

  it('offers a retry for files whose upload failed, without choosing again', async () => {
    api.uploadBatchFile.mockImplementationOnce(() => ({ promise: Promise.reject(new Error('Network dropped.')) }))
    render(<AddBatchFlow onDone={vi.fn()} />)
    choose(folder())
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Upload batch' }))
    await user.click(await screen.findByRole('button', { name: 'Retry missing files' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('All files verified.'))
    expect(api.uploadBatchFile).toHaveBeenCalledTimes(3)
  })
})
