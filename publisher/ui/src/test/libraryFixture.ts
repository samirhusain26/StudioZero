import type { LibraryBatch, LibraryEpisode, LibraryResponse } from '../api/types'
import { PLATFORMS } from '../api/types'

export function libEpisode(n: number, over: Partial<LibraryEpisode> = {}): LibraryEpisode {
  const id = `scalar-clues-00${n}`
  return {
    episodeId: id, revision: 1, batchId: '2026-10-b01', questionId: `scalar:Q${n}:clues`, game: 'scalar', format: 'progressive-clues',
    difficulty: 'moderate', status: 'reviewable', statusLabel: 'Ready for review', metadataSha256: 'c'.repeat(64), videoSha256: 'a'.repeat(64),
    coverSha256: 'b'.repeat(64), videoUrl: `/api/media/videos/${'a'.repeat(64)}.mp4?t=1`, coverUrl: null, media: null, videoRemovedAt: null,
    platforms: Object.fromEntries(PLATFORMS.map((p) => [p, { eligible: true, reason: null }])) as LibraryEpisode['platforms'],
    problems: [], approvals: [], currentApproval: null, inManifest: false, deletable: true, legacy: false, variants: [], postedOn: [],
    episode: { creative: { hook: `Hook ${n}`, question: `Question ${n}?`, clues: [], choices: null, answer: 'X', answerAliases: [], explanation: '' } } as unknown as LibraryEpisode['episode'],
    ...over,
  }
}

export function libBatch(batchId: string, episodeCount: number, importedAt: string, over: Partial<LibraryBatch> = {}): LibraryBatch {
  return { batchId, origin: 'mac', createdAt: null, importedAt, batchJsonSha256: 'd'.repeat(64), generatorDirty: false, repoCommit: null, warnings: [], episodeCount, awaitingFiles: 0, ...over }
}

export function libraryFixture(): LibraryResponse {
  return {
    generatedAt: '2026-10-08T12:00:00Z',
    displayTimezone: 'UTC',
    batches: [libBatch('legacy-2026-10-05', 1, '2026-10-05T00:00:00Z', { origin: 'legacy' }), libBatch('2026-10-b01', 3, '2026-10-07T00:00:00Z')],
    episodes: [
      libEpisode(1),
      libEpisode(2, { status: 'approved', statusLabel: 'Approved' }),
      libEpisode(3, { status: 'withdrawn', statusLabel: 'Withdrawn' }),
      libEpisode(4, { batchId: 'legacy-2026-10-05', episodeId: 'scalar-legacy-001' }),
    ],
  }
}
