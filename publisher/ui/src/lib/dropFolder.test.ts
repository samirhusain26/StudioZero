import { describe, expect, it } from 'vitest'
import { findBatchFolder } from './batchFolder'
import { dragHasFiles, entriesFromDataTransfer, filesFromEntries, type EntryLike } from './dropFolder'

function fileEntry(fullPath: string, size = 10): EntryLike {
  const name = fullPath.split('/').pop() ?? fullPath
  return {
    isFile: true,
    isDirectory: false,
    name,
    fullPath,
    file: (ok) => ok(new File([new Uint8Array(size)], name)),
  }
}

/** A directory whose reader returns children in batches of `batch` (like Chrome's 100), then []. */
function dirEntry(fullPath: string, children: EntryLike[], batch = 2): EntryLike {
  return {
    isFile: false,
    isDirectory: true,
    name: fullPath.split('/').pop() ?? fullPath,
    fullPath,
    createReader: () => {
      let offset = 0
      return {
        readEntries: (ok) => {
          const next = children.slice(offset, offset + batch)
          offset += batch
          setTimeout(() => ok(next), 0)
        },
      }
    },
  }
}

const batchTree = () =>
  dirEntry('/2026-10-b01', [
    fileEntry('/2026-10-b01/batch.json'),
    fileEntry('/2026-10-b01/READY_FOR_UPLOAD'),
    dirEntry('/2026-10-b01/videos', [fileEntry('/2026-10-b01/videos/a.mp4', 1000), fileEntry('/2026-10-b01/videos/b.mp4', 1000), fileEntry('/2026-10-b01/videos/c.mp4', 1000)]),
    dirEntry('/2026-10-b01/covers', [fileEntry('/2026-10-b01/covers/a.jpg', 100)]),
    dirEntry('/2026-10-b01/review', [fileEntry('/2026-10-b01/review/index.html')]),
    fileEntry('/2026-10-b01/.DS_Store'),
  ])

describe('filesFromEntries', () => {
  it('walks a dropped folder into the same path list the folder picker gives', async () => {
    const files = await filesFromEntries([batchTree()])
    expect(files.map((f) => f.path)).toEqual([
      '2026-10-b01/batch.json',
      '2026-10-b01/READY_FOR_UPLOAD',
      '2026-10-b01/videos/a.mp4',
      '2026-10-b01/videos/b.mp4',
      '2026-10-b01/videos/c.mp4',
      '2026-10-b01/covers/a.jpg',
      '2026-10-b01/review/index.html',
      '2026-10-b01/.DS_Store',
    ])
    expect(files[2]).toMatchObject({ size: 1000 })
    expect(files[2]?.file.name).toBe('a.mp4')
    expect(findBatchFolder(files)).toEqual({
      root: '2026-10-b01/',
      batchJson: '2026-10-b01/batch.json',
      ready: '2026-10-b01/READY_FOR_UPLOAD',
      ignored: 2,
    })
  })

  it('handles the folder contents dropped as separate items (no common folder)', async () => {
    const files = await filesFromEntries([fileEntry('/batch.json'), fileEntry('/READY_FOR_UPLOAD'), dirEntry('/videos', [fileEntry('/videos/a.mp4')])])
    expect(files.map((f) => f.path)).toEqual(['batch.json', 'READY_FOR_UPLOAD', 'videos/a.mp4'])
    expect(findBatchFolder(files)).toMatchObject({ root: '', batchJson: 'batch.json' })
  })

  it('rejects when a file cannot be read', async () => {
    const broken: EntryLike = { isFile: true, isDirectory: false, name: 'x', fullPath: '/x', file: (_ok, fail) => fail?.(new Error('denied')) }
    await expect(filesFromEntries([broken])).rejects.toThrow('denied')
  })
})

describe('entriesFromDataTransfer', () => {
  it('takes entries from file items and refuses browsers without webkitGetAsEntry', () => {
    const entry = fileEntry('/a')
    const withEntries = { items: [{ kind: 'file', webkitGetAsEntry: () => entry }], types: ['Files'] } as unknown as DataTransfer
    expect(entriesFromDataTransfer(withEntries)).toEqual([entry])
    expect(dragHasFiles(withEntries)).toBe(true)
    const without = { items: [{ kind: 'file' }], types: ['Files'] } as unknown as DataTransfer
    expect(entriesFromDataTransfer(without)).toBeNull()
    expect(entriesFromDataTransfer(null)).toBeNull()
    expect(dragHasFiles({ types: ['text/plain'] } as unknown as DataTransfer)).toBe(false)
  })
})
