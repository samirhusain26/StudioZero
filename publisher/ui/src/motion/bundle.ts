/**
 * The Studio job bundle (engines/motion/pipeline/web-jobs.mjs writes <batch>/review/web-jobs.json on the Mac or in a
 * Claude Code session): everything the browser needs to export and package one batch. It may name unposted answers,
 * so it is opened from the device's own files and kept only in this browser. Pure checks; no I/O.
 */

export interface JobInput {
  episodeId: string
  batchId: string
  revision: number
  questionKey: string
  questionId: string
  kitVersion: string
  styleId: string
  propsHash: string
  props: {
    durationInFrames: number
    styleId: string
    q: { game: string; format: string } & Record<string, unknown>
    timing: { infoComplete: number } & Record<string, number | number[]>
    music: { bed: string; volume: number }
  } & Record<string, unknown>
}

export interface JobBundle {
  kind: 'studio-motion-jobs'
  version: 1
  batchId: string
  project: string
  createdAt: string
  repoCommit: string
  studio: unknown
  projectManifest: { id: string } & Record<string, unknown>
  set: { name: string; config: { batches: string[]; experimentId: string; variantId: string | null; reviewer: string } }
  questions: { snapshotId: string; snapshotHash: string; questionsHash: string; questions: ({ key: string } & Record<string, unknown>)[] }
  verification: { results: { key: string; status: string; resolution?: string }[] } | null
  verReport: string
  recipes: Record<string, unknown>
  fonts: Record<string, string[]>
  beds: Record<string, { bed: string } & Record<string, unknown>>
  jobs: JobInput[]
}

const BATCH_ID = /^\d{4}-(0[1-9]|1[0-2])-[a-z0-9]+(-[a-z0-9]+)*$/
const EPISODE_ID = /^[a-z0-9-]{1,80}$/
const HEX = /^[0-9a-f]{64}$/
export const MAX_BUNDLE_BYTES = 20_000_000

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

/**
 * Parse and check a bundle. `assets` (paths from GET /api/assets/motion/manifest), when given, must contain every music
 * bed the jobs use. Returns the bundle or the problems, in plain language.
 */
export function parseBundle(text: string, assets?: ReadonlySet<string>): { bundle: JobBundle | null; problems: string[] } {
  if (text.length > MAX_BUNDLE_BYTES) return { bundle: null, problems: ['The file is too large to be a Studio job bundle.'] }
  let doc: unknown
  try {
    doc = JSON.parse(text)
  } catch {
    return { bundle: null, problems: ['The file is not JSON. Choose review/web-jobs.json from the batch folder.'] }
  }
  if (!isObj(doc) || doc.kind !== 'studio-motion-jobs' || doc.version !== 1)
    return { bundle: null, problems: ['This is not a Studio job bundle (web-jobs.json, version 1).'] }
  const problems: string[] = []
  if (typeof doc.batchId !== 'string' || !BATCH_ID.test(doc.batchId)) problems.push('The bundle has no valid batch id.')
  if (doc.project !== 'scalargame') problems.push(`Project ${String(doc.project)} has no browser export yet.`)
  if (typeof doc.repoCommit !== 'string' || !/^[0-9a-f]{40}$/.test(doc.repoCommit)) problems.push('The bundle has no repo commit.')
  for (const key of ['studio', 'projectManifest', 'set', 'questions', 'recipes', 'fonts', 'beds'] as const)
    if (!isObj(doc[key])) problems.push(`The bundle has no ${key}.`)
  const jobs = Array.isArray(doc.jobs) ? doc.jobs : []
  if (!jobs.length) problems.push('The bundle has no jobs.')
  const seen = new Set<string>()
  const beds = isObj(doc.beds) ? doc.beds : {}
  for (const job of jobs) {
    if (!isObj(job) || typeof job.episodeId !== 'string' || !EPISODE_ID.test(job.episodeId)) {
      problems.push('A job has no valid episode id.')
      continue
    }
    const id = job.episodeId
    if (seen.has(id)) problems.push(`${id} appears twice.`)
    seen.add(id)
    const props = job.props
    if (job.batchId !== doc.batchId) problems.push(`${id} belongs to batch ${String(job.batchId)}.`)
    if (typeof job.propsHash !== 'string' || !HEX.test(job.propsHash)) problems.push(`${id} has no props hash.`)
    if (!isObj(props) || !Number.isInteger(props.durationInFrames) || (props.durationInFrames as number) <= 0 || !isObj(props.q) || !isObj(props.music) || !isObj(props.timing)) {
      problems.push(`${id} has no usable props.`)
      continue
    }
    const bed = String(props.music.bed ?? '')
    const bedId = bed.replace(/\.m4a$/, '')
    if (!isObj(beds[bedId])) problems.push(`${id}: music bed ${bedId} is not in the bundle.`)
    if (assets && !assets.has(`episodes/music/${bed}`)) problems.push(`${id}: music bed ${bedId} is not on this Pi (retired or local-only).`)
    if (typeof job.styleId !== 'string' || !(isObj(doc.fonts) && Array.isArray(doc.fonts[job.styleId]))) problems.push(`${id}: style ${String(job.styleId)} is not in the bundle.`)
  }
  return problems.length ? { bundle: null, problems } : { bundle: doc as unknown as JobBundle, problems: [] }
}

/** Cover frame as render.mjs picks it: half a second after the information is complete. */
export function coverFrame(job: JobInput, fps = 30): number {
  return Math.round((job.props.timing.infoComplete + 0.5) * fps)
}
