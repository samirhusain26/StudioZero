/**
 * Next-batch hand-off (REBUILD_CONTRACTS.md §3): the draft brief template, the exact
 * "Copy prompt for Claude" text and the feedback.json export.
 */
import type { AccountStats, FeedbackItem, FeedbackTag, NextBatchInfo, PostMetrics } from '../api/types'
import { FEEDBACK_TAGS } from '../api/types'
import { SAFETY_LINES } from './promptSafety'

export const TAG_LABELS: Record<FeedbackTag, string> = {
  keep: 'Keep',
  tweak: 'Tweak',
  drop: 'Drop',
  'hook-weak': 'Weak hook',
  'too-hard': 'Too hard',
  'too-easy': 'Too easy',
  'great-reveal': 'Great reveal',
  'visual-issue': 'Visual issue',
  'fact-check': 'Fact-check',
  music: 'Music',
}

export const FEEDBACK_NOTE_LIMIT = 2000

const WORKED: readonly FeedbackTag[] = ['keep', 'great-reveal']
const AVOID: readonly FeedbackTag[] = ['drop']
const FIX: readonly FeedbackTag[] = FEEDBACK_TAGS.filter((t) => !WORKED.includes(t) && !AVOID.includes(t))

export function tagLabel(tag: string): string {
  return (TAG_LABELS as Record<string, string>)[tag] ?? tag
}

function oneLine(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}

function itemLine(item: FeedbackItem, tags: readonly FeedbackTag[]): string {
  const shown = item.tags.filter((t) => tags.includes(t)).map(tagLabel)
  const what = [item.game, item.format, item.styleId].filter(Boolean).join(' / ')
  const note = oneLine(item.note)
  return `- ${item.episodeId} rev ${item.revision} (${what})${shown.length ? `: ${shown.join(', ')}` : ''}${note ? ` — ${note}` : ''}`
}

function section(items: FeedbackItem[], tags: readonly FeedbackTag[], empty: string): string[] {
  const matching = items.filter((i) => i.tags.some((t) => tags.includes(t)))
  return matching.length ? matching.map((i) => itemLine(i, tags)) : [`- ${empty}`]
}

/** The brief's sections that the Studio prompt builder fills; placeholders otherwise. */
export interface BriefChoices {
  goals?: string[]
  mix: string[]
  experiments?: string[]
}

/** The "## Mix" placeholder lines, with the choices taken from the catalog. */
export function placeholderMix(games: readonly string[], formats: readonly string[]): string[] {
  return [`- Games: <choose from ${games.join(', ')}>`, `- Formats: <choose from ${formats.join(', ')}>`, '- Episodes: <how many>']
}

/** The editable draft brief, prefilled from open feedback and the last retro. */
export function buildBriefTemplate(info: Pick<NextBatchInfo, 'nextBatchId' | 'openFeedback' | 'lastRetro'>, choices: BriefChoices): string {
  const items = info.openFeedback
  // Notes without any tag still matter: list them under "What to fix".
  const untagged = items.filter((i) => i.tags.length === 0 && oneLine(i.note))
  const fix = [...section(items, FIX, 'No fixes requested.'), ...untagged.map((i) => itemLine(i, []))]
  if (fix.length > 1 && fix[0] === '- No fixes requested.') fix.shift()
  const retro = info.lastRetro
  return [
    `# Brief: ${info.nextBatchId}`,
    '',
    `Batch id: ${info.nextBatchId}`,
    '',
    '## Goals',
    ...(choices.goals?.length ? choices.goals : ['- <what this batch should achieve>']),
    '',
    '## Mix',
    ...choices.mix,
    '',
    '## What worked',
    ...section(items, WORKED, 'No “keep” or “great reveal” feedback yet.'),
    '',
    '## What to fix',
    ...fix,
    '',
    '## Avoid',
    ...section(items, AVOID, 'Nothing marked “drop”.'),
    '',
    '## Experiments',
    ...(choices.experiments?.length ? choices.experiments : ['- <one thing to try>']),
    '',
    '## Last retro',
    retro
      ? `- library/_retros/${retro.batchId}.md (uploaded to the Pi ${retro.uploadedAt.slice(0, 10)})`
      : '- No retro uploaded yet.',
    '',
  ].join('\n')
}

/** Exactly the text "Copy prompt for Claude" puts on the clipboard (§3), ending with the fixed safety lines. */
export function buildCopyPrompt(nextBatchId: string, brief: string): string {
  return `/video-batch brief ${nextBatchId}\n\n${brief}\n\nFeedback file: library/_inbox/feedback-${nextBatchId}.json\n\n${SAFETY_LINES.join('\n')}`
}

export function feedbackFileName(nextBatchId: string): string {
  return `feedback-${nextBatchId}.json`
}

export interface FeedbackExport {
  schemaVersion: 1
  kind: 'scalar-next-batch-feedback'
  exportedAt: string
  fromCommit: string | null
  nextBatchId: string
  brief: string
  lastRetro: { batchId: string; text: string } | null
  feedback: {
    episodeId: string
    revision: number
    batchId: string
    questionId: string
    game: string
    format: string
    styleId: string
    tags: FeedbackTag[]
    note: string
    updatedAt: string
  }[]
  performance: { platform: string; status: string; at: string | null; permalink: string | null; metrics: PostMetrics | null }[]
  accounts: AccountStats[]
}

/** The feedback.json document (§3 schema, fields in contract order). */
export function buildFeedbackExport(args: { info: NextBatchInfo; brief: string; fromCommit: string | null; exportedAt: Date }): FeedbackExport {
  const { info, brief, fromCommit, exportedAt } = args
  return {
    schemaVersion: 1,
    kind: 'scalar-next-batch-feedback',
    exportedAt: exportedAt.toISOString().replace(/\.\d{3}Z$/, 'Z'),
    fromCommit,
    nextBatchId: info.nextBatchId,
    brief,
    lastRetro: info.lastRetro ? { batchId: info.lastRetro.batchId, text: info.lastRetro.text } : null,
    feedback: info.openFeedback.map((f) => ({
      episodeId: f.episodeId,
      revision: f.revision,
      batchId: f.batchId,
      questionId: f.questionId,
      game: f.game,
      format: f.format,
      styleId: f.styleId,
      tags: [...f.tags],
      note: f.note,
      updatedAt: f.updatedAt,
    })),
    performance: info.performance.map((p) => ({ platform: p.platform, status: p.status, at: p.at, permalink: p.permalink, metrics: p.metrics ?? null })),
    accounts: info.accounts.map((a) => ({ ...a, totals: { ...a.totals } })),
  }
}

export function feedbackJson(doc: FeedbackExport): string {
  return `${JSON.stringify(doc, null, 2)}\n`
}

/** Open feedback grouped by batch, then episode (stable, sorted). */
export function groupFeedback(items: FeedbackItem[]): { batchId: string; items: FeedbackItem[] }[] {
  const groups = new Map<string, FeedbackItem[]>()
  for (const item of items) groups.set(item.batchId, [...(groups.get(item.batchId) ?? []), item])
  return [...groups.entries()]
    .sort(([a], [b]) => (a < b ? 1 : a > b ? -1 : 0))
    .map(([batchId, list]) => ({
      batchId,
      items: [...list].sort((x, y) => (x.episodeId === y.episodeId ? x.revision - y.revision : x.episodeId < y.episodeId ? -1 : 1)),
    }))
}
