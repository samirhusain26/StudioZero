/** Per-episode export status for Studio › Export, from the bundle and what this browser has stored. Pure. */
import type { JobBundle } from './bundle'
import type { StoredExport } from './store'

export type EpisodeStatus = 'pending' | 'interrupted' | 'stale' | 'failed' | 'passed'

export interface EpisodeRow {
  episodeId: string
  format: string
  game: string
  status: EpisodeStatus
  export: StoredExport | null
}

export const STATUS_LABELS: Record<EpisodeStatus, string> = {
  pending: 'Not exported',
  interrupted: 'Interrupted: export again',
  stale: 'Bundle changed: export again',
  failed: 'Failed checks',
  passed: 'Passed checks',
}

export function episodeRows(bundle: JobBundle, exports: readonly StoredExport[], running: string | null): EpisodeRow[] {
  const byId = new Map(exports.map((e) => [e.episodeId, e]))
  return bundle.jobs.map((job) => {
    const done = byId.get(job.episodeId) ?? null
    const status: EpisodeStatus = !done
      ? running === job.episodeId
        ? 'interrupted'
        : 'pending'
      : done.propsHash !== job.propsHash
        ? 'stale'
        : done.errors.length
          ? 'failed'
          : 'passed'
    return { episodeId: job.episodeId, format: job.props.q.format, game: job.props.q.game, status, export: done }
  })
}

/** Everything exported, current and passing: the batch can be packaged. */
export function readyToPackage(rows: readonly EpisodeRow[]): boolean {
  return rows.length > 0 && rows.every((r) => r.status === 'passed')
}

/** The next episodes "Export all" should do, in bundle order. */
export function remaining(rows: readonly EpisodeRow[]): string[] {
  return rows.filter((r) => r.status !== 'passed').map((r) => r.episodeId)
}

/** A phone-sized touch device: export one episode at a time there; a laptop is the default for whole batches. */
export function isPhone(nav: { userAgentData?: { mobile?: boolean } } | undefined, coarsePointerSmallScreen: boolean): boolean {
  return nav?.userAgentData?.mobile === true || coarsePointerSmallScreen
}
