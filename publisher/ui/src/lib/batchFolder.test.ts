import { describe, expect, it } from 'vitest'
import type { ExpectedFile } from '../api/types'
import { checkReadyMarker, expectedFilesIn, findBatchFolder, type FolderFile } from './batchFolder'

const f = (path: string, size = 10): FolderFile => ({ path, size })
const batch = (root: string, ready = true) => [
  f(`${root}batch.json`),
  ...(ready ? [f(`${root}READY_FOR_UPLOAD`)] : []),
  f(`${root}videos/scalar-clues-002.mp4`, 1000),
  f(`${root}covers/scalar-clues-002.jpg`, 100),
  f(`${root}review/index.html`),
  f(`${root}review/frames/scalar-clues-002/00-hook.png`),
  f(`${root}review/jobs/scalar-clues-002/out.mp4`),
]
function expected(name: string, kind: 'video' | 'cover'): ExpectedFile {
  return {
    file: `${kind === 'video' ? 'videos' : 'covers'}/${name}`,
    name,
    kind,
    episodeId: 'scalar-clues-002',
    revision: 1,
    sha256: 'a'.repeat(64),
    bytes: 1,
    present: false,
  }
}

describe('findBatchFolder', () => {
  it('finds a finalized batch folder and counts what it will not upload', () => {
    expect(findBatchFolder(batch('2026-10-b01/'))).toEqual({
      root: '2026-10-b01/',
      batchJson: '2026-10-b01/batch.json',
      ready: '2026-10-b01/READY_FOR_UPLOAD',
      ignored: 3,
    })
  })

  it('works when the folder is chosen one level up (library/<batchId>/)', () => {
    const found = findBatchFolder([...batch('library/2026-10-b01/'), f('library/.DS_Store')])
    expect(found).toMatchObject({ root: 'library/2026-10-b01/', ignored: 4 })
  })

  it('refuses a folder without batch.json, with several batches, or not finalized', () => {
    expect(findBatchFolder([f('videos/a.mp4'), f('covers/a.jpg')])).toMatch(/No batch.json/)
    expect(findBatchFolder([...batch('library/a/'), ...batch('library/b/')])).toMatch(/holds 2 batches \(a, b\)/)
    expect(findBatchFolder(batch('2026-10-b01/', false))).toMatch(/not finalized/)
  })
})

describe('checkReadyMarker', () => {
  const sha = 'b'.repeat(64)
  it('accepts the marker finalize wrote for this batch.json', () => {
    expect(checkReadyMarker(JSON.stringify({ schemaVersion: 1, batchJsonSha256: sha }), sha)).toBeNull()
  })
  it('rejects a stale, malformed or incomplete marker', () => {
    expect(checkReadyMarker(JSON.stringify({ batchJsonSha256: 'c'.repeat(64) }), sha)).toMatch(/changed after finalize/)
    expect(checkReadyMarker('not json', sha)).toMatch(/not valid JSON/)
    expect(checkReadyMarker('{}', sha)).toMatch(/no batchJsonSha256/)
  })
})

describe('expectedFilesIn', () => {
  it('selects exactly the listed videos and covers by path, never review copies', () => {
    const files = [...batch('2026-10-b01/'), f('2026-10-b01/review/videos/scalar-clues-002.mp4'), f('2026-10-b01/videos/stray.mp4')]
    const picked = expectedFilesIn(files, '2026-10-b01/', [expected('scalar-clues-002.mp4', 'video'), expected('scalar-clues-002.jpg', 'cover')])
    expect(picked.map((p) => p.path)).toEqual(['2026-10-b01/videos/scalar-clues-002.mp4', '2026-10-b01/covers/scalar-clues-002.jpg'])
  })
})
