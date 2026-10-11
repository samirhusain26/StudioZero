/**
 * The Mac side of "Make a batch" (docs/PI_UI_REDESIGN_PLAN.md §4.7): a per-batch-id, browser-local checklist.
 * Purely a memory aid — the Pi never sees it. A batch id is "done" once a batch with that id is in the
 * library; the next batch id then moves on (NN = 1 + the highest bNN imported), so checklists for lower
 * numbers are pruned.
 */
export const MAKE_CHECKPOINTS = [
  { id: 'c0', label: 'Checkpoint 0', detail: 'brief and open questions' },
  { id: 'c1', label: 'Checkpoint 1', detail: 'questions, answers, choices, difficulty' },
  { id: 'c2', label: 'Checkpoint 2', detail: 'pilot video per game (only if the brief asks)' },
  { id: 'c3', label: 'Checkpoint 3', detail: 'review/index.html, covers.png, checkpoint3.md' },
  { id: 'finalize', label: 'Finalize', detail: 'say “finalize” → READY_FOR_UPLOAD is written; the folder is frozen' },
] as const

export type CheckpointId = (typeof MAKE_CHECKPOINTS)[number]['id']

export interface MakeProgress {
  batchId: string
  /** The brief was edited, the prompt copied or feedback.json downloaded in this browser. */
  started: boolean
  checks: CheckpointId[]
}

export const MAKE_KEY_PREFIX = 'scalar-make-'
/** Fired on window after a write, so the loop strip can follow ticks made on another screen. */
export const MAKE_EVENT = 'scalar-make-change'
const NUMBERED = /^\d{4}-\d{2}-b(\d{2,})$/

function safeLocal(): Storage | null {
  try {
    // window.localStorage, not the bare global (Node 24 defines a different, unusable one).
    return typeof window === 'undefined' ? null : window.localStorage
  } catch {
    return null
  }
}

function batchNumber(batchId: string): number | null {
  const m = NUMBERED.exec(batchId)
  return m ? Number(m[1]) : null
}

function keys(storage: Storage): string[] {
  const out: string[] = []
  for (let i = 0; i < storage.length; i++) {
    const key = storage.key(i)
    if (key?.startsWith(MAKE_KEY_PREFIX)) out.push(key)
  }
  return out
}

function parse(batchId: string, raw: string | null): MakeProgress | null {
  if (!raw) return null
  try {
    const data = JSON.parse(raw) as { started?: unknown; checks?: unknown }
    const known = new Set<string>(MAKE_CHECKPOINTS.map((c) => c.id))
    const checks = Array.isArray(data.checks) ? data.checks.filter((c): c is CheckpointId => typeof c === 'string' && known.has(c)) : []
    return { batchId, started: data.started === true || checks.length > 0, checks: [...new Set(checks)] }
  } catch {
    return null
  }
}

export function emptyMake(batchId: string): MakeProgress {
  return { batchId, started: false, checks: [] }
}

/**
 * The checklist for `batchId`. The id carries the current UTC month, so after a month rollover the same
 * bNN under the old month is carried over.
 */
export function readMake(batchId: string, storage: Storage | null = safeLocal()): MakeProgress {
  if (!storage) return emptyMake(batchId)
  try {
    const own = parse(batchId, storage.getItem(MAKE_KEY_PREFIX + batchId))
    if (own) return own
    const n = batchNumber(batchId)
    if (n === null) return emptyMake(batchId)
    const carried = keys(storage).find((k) => batchNumber(k.slice(MAKE_KEY_PREFIX.length)) === n)
    return (carried && parse(batchId, storage.getItem(carried))) || emptyMake(batchId)
  } catch {
    return emptyMake(batchId)
  }
}

export function writeMake(progress: MakeProgress, storage: Storage | null = safeLocal()): void {
  try {
    storage?.setItem(MAKE_KEY_PREFIX + progress.batchId, JSON.stringify({ started: progress.started, checks: progress.checks }))
  } catch {
    // Storage blocked: the checklist only lasts while this page stays open.
  }
  if (typeof window !== 'undefined') window.dispatchEvent(new Event(MAKE_EVENT))
}

/** Remove checklists for batches that have arrived (lower bNN than the next id) or are malformed. */
export function pruneMake(nextBatchId: string, storage: Storage | null = safeLocal()): void {
  const next = batchNumber(nextBatchId)
  if (!storage || next === null) return
  try {
    for (const key of keys(storage)) {
      const n = batchNumber(key.slice(MAKE_KEY_PREFIX.length))
      if (n === null || n < next) storage.removeItem(key)
    }
  } catch {
    // ignore
  }
}

/** Finalize ticked: the batch should be on its way to the Pi. */
export function makeComplete(progress: MakeProgress | null | undefined): boolean {
  return Boolean(progress?.checks.includes('finalize'))
}
