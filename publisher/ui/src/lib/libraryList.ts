/**
 * Library list (docs/PI_UI_REDESIGN_PLAN.md §4.2): batch chips, a To review / Approved / All filter and
 * the ordered list the review screen steps through with Next / Previous. The choice is remembered for
 * this tab (sessionStorage) so the review screen walks the same list the owner was looking at.
 */
import type { LibraryEpisode, LibraryResponse } from '../api/types'

export const LIBRARY_FILTERS = [
  { id: 'review', label: 'To review' },
  { id: 'approved', label: 'Approved' },
  { id: 'all', label: 'All' },
] as const

export type LibraryFilterId = (typeof LIBRARY_FILTERS)[number]['id']

export interface LibraryListState {
  /** '' = all batches. */
  batchId: string
  filter: LibraryFilterId
}

export const DEFAULT_LIST: LibraryListState = { batchId: '', filter: 'review' }
export const LIST_KEY = 'scalar-library-list'

/** Waiting for a decision: ready for review, or withdrawn (may be approved again). */
export function needsReview(e: LibraryEpisode): boolean {
  return e.status === 'reviewable' || e.status === 'withdrawn'
}

export function matchesFilter(e: LibraryEpisode, filter: LibraryFilterId): boolean {
  return filter === 'all' || (filter === 'review' ? needsReview(e) : e.status === 'approved')
}

/**
 * The episodes a list state shows, in library order. `keep` stays in the list even when it no longer matches
 * (an episode just approved from the review screen keeps its place, so Next still goes to the following one).
 */
export function listEpisodes(
  data: Pick<LibraryResponse, 'episodes'>,
  state: LibraryListState,
  keep?: { episodeId: string; revision: number },
): LibraryEpisode[] {
  return data.episodes.filter(
    (e) =>
      (keep && e.episodeId === keep.episodeId && e.revision === keep.revision) ||
      ((!state.batchId || e.batchId === state.batchId) && matchesFilter(e, state.filter)),
  )
}

export function filterCounts(data: Pick<LibraryResponse, 'episodes'>, batchId: string): Record<LibraryFilterId, number> {
  const inBatch = data.episodes.filter((e) => !batchId || e.batchId === batchId)
  return { review: inBatch.filter(needsReview).length, approved: inBatch.filter((e) => e.status === 'approved').length, all: inBatch.length }
}

/** Batch chips, newest import first, each with its episode count. */
export function batchChips(data: Pick<LibraryResponse, 'batches'>): { batchId: string; label: string; count: number }[] {
  return [...data.batches]
    .sort((a, b) => (b.importedAt ?? '').localeCompare(a.importedAt ?? '') || b.batchId.localeCompare(a.batchId))
    .map((b) => ({ batchId: b.batchId, label: b.batchId.startsWith('legacy-') ? 'legacy' : b.batchId, count: b.episodeCount }))
}

/** Shown episodes that "Approve all shown" would approve. */
export function approvableShown(shown: LibraryEpisode[]): LibraryEpisode[] {
  return shown.filter((e) => needsReview(e) && e.problems.length === 0)
}

export function canApprove(e: LibraryEpisode | null | undefined): boolean {
  return Boolean(e && needsReview(e) && e.problems.length === 0)
}

/** Where an episode sits in the list, and its neighbours (null at either end, or when it is not in the list). */
export function position(list: LibraryEpisode[], episodeId: string, revision: number) {
  const i = list.findIndex((e) => e.episodeId === episodeId && e.revision === revision)
  return {
    index: i,
    total: list.length,
    previous: i > 0 ? (list[i - 1] ?? null) : null,
    next: i >= 0 && i < list.length - 1 ? (list[i + 1] ?? null) : null,
  }
}

function safeSession(): Storage | null {
  try {
    return typeof sessionStorage === 'undefined' ? null : sessionStorage
  } catch {
    return null
  }
}

export function readListState(storage: Storage | null = safeSession()): LibraryListState {
  try {
    const data = JSON.parse(storage?.getItem(LIST_KEY) ?? 'null') as Partial<LibraryListState> | null
    const filter = LIBRARY_FILTERS.some((f) => f.id === data?.filter) ? (data?.filter as LibraryFilterId) : DEFAULT_LIST.filter
    return { batchId: typeof data?.batchId === 'string' ? data.batchId : '', filter }
  } catch {
    return DEFAULT_LIST
  }
}

export function writeListState(state: LibraryListState, storage: Storage | null = safeSession()): void {
  try {
    storage?.setItem(LIST_KEY, JSON.stringify(state))
  } catch {
    // Storage blocked: the list falls back to To review / all batches.
  }
}

/** The reviewer name recorded with approvals, remembered on this device. */
export const REVIEWER_KEY = 'scalar-reviewer'

export function readReviewer(): string {
  try {
    return window.localStorage.getItem(REVIEWER_KEY) || 'owner'
  } catch {
    return 'owner'
  }
}

export function writeReviewer(name: string): void {
  try {
    window.localStorage.setItem(REVIEWER_KEY, name)
  } catch {
    // ignore
  }
}
