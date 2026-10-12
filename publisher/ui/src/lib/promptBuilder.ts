/**
 * Studio prompt builder, mode 1: a batch from existing formats (brief: "Prompt builder"). Pure functions; every
 * option comes from the catalog, presets live only in this browser, nothing is written to the Pi.
 *
 * Scalargame → the `/video-batch brief <batchId>` hand-off (nextBatch.ts, REBUILD_CONTRACTS §3).
 * Originals → the originals playbook prompt as text (the skill itself arrives in Phase 5).
 * Every prompt ends with SAFETY_LINES.
 */
import type { Catalog, CatalogProject, NextBatchInfo } from '../api/types'
import { bedsFor, catalogFormats, catalogGames, engineOf, formatOf, formatRenderable, projectOf, stylesFor } from './catalog'
import { buildBriefTemplate, buildCopyPrompt, placeholderMix } from './nextBatch'
import { SAFETY_LINES } from './promptSafety'

/** Episodes per difficulty: approachable, moderate, challenging. */
export type DifficultyMix = [number, number, number]

export interface ScopeRow {
  format: string
  count: number
  /** Scalargame only (the set's CONFIG.mix); ignored for projects without games. */
  mix: DifficultyMix
}

export interface BatchPlan {
  project: string
  batchId: string
  goal: string
  scope: ScopeRow[]
  /** Spare questions per format (Scalargame). */
  spares: number
  /** One pilot per game first, then Checkpoint 2 (Scalargame). */
  pilots: boolean
  /** game → styleId (Scalargame). */
  styles: Record<string, string>
  /** format → CALM or a bed id (Scalargame). */
  music: Record<string, string>
  experimentId: string
  prefer: string
  avoid: string
  /** Originals: one title or story idea per line. */
  subjects: string
  notes: string
}

export const CALM = 'calm'
export const MAX_PER_FORMAT = 30
export const MAX_SPARES = 5
export const TEXT_LIMIT = 2000
const BATCH_ID = /^\d{4}-(0[1-9]|1[0-2])-[a-z0-9]+(-[a-z0-9]+)*$/
const EXPERIMENT_ID = /^[a-z0-9][a-z0-9-]{0,63}$/
const DIFFICULTY_NAMES = ['approachable', 'moderate', 'challenging'] as const

function hasGames(project: CatalogProject): boolean {
  return Boolean(project.games?.length)
}

function oneLine(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}

function lines(text: string): string[] {
  return text
    .split('\n')
    .map((l) => oneLine(l.replace(/^[-*]\s+/, '')))
    .filter(Boolean)
}

function isCount(n: unknown, max: number): n is number {
  return typeof n === 'number' && Number.isInteger(n) && n >= 0 && n <= max
}

/** An even split of `count` over the three difficulties (extra episodes go to the easier ones first). */
export function evenMix(count: number): DifficultyMix {
  const base = Math.floor(count / 3)
  const extra = count % 3
  return [base + (extra > 0 ? 1 : 0), base + (extra > 1 ? 1 : 0), base]
}

/** The starting plan for a project: Scalargame three per format, Originals one episode of its first format. */
export function defaultPlan(catalog: Catalog, projectId: string, batchId: string): BatchPlan {
  const project = projectOf(catalog, projectId)
  const formats = (project?.formats ?? []).filter((f) => formatRenderable(catalog, f))
  const games = project && hasGames(project)
  const scope = formats.map((f, i) => {
    const count = games ? 3 : i === 0 ? 1 : 0
    return { format: f.id, count, mix: evenMix(count) }
  })
  const styles: Record<string, string> = {}
  const music: Record<string, string> = {}
  if (games) {
    for (const game of project.games ?? []) {
      const style = stylesFor(catalog, game.id)[0]
      if (style) styles[game.id] = style.id
    }
    for (const f of formats) music[f.id] = CALM
  }
  return {
    project: projectId,
    batchId,
    goal: '',
    scope,
    spares: games ? 1 : 0,
    pilots: false,
    styles,
    music,
    experimentId: '',
    prefer: '',
    avoid: '',
    subjects: '',
    notes: '',
  }
}

export function totalEpisodes(plan: BatchPlan): number {
  return plan.scope.reduce((sum, row) => sum + (isCount(row.count, MAX_PER_FORMAT) ? row.count : 0), 0)
}

/** Games that have at least one episode in the plan (Scalargame). */
export function plannedGames(catalog: Catalog, plan: BatchPlan): string[] {
  const games = new Set(plan.scope.filter((r) => r.count > 0).map((r) => formatOf(catalog, plan.project, r.format)?.game).filter(Boolean))
  return catalogGames(catalog).filter((g) => games.has(g))
}

/** Everything that keeps the plan from becoming a prompt; empty = ready. Plain language, one line each. */
export function planProblems(catalog: Catalog, plan: BatchPlan): string[] {
  const project = projectOf(catalog, plan.project)
  if (!project) return [`Unknown project “${plan.project}”.`]
  const problems: string[] = []
  if (!BATCH_ID.test(plan.batchId) || plan.batchId.length > 64) problems.push('Batch id must look like YYYY-MM-name (lowercase letters, digits, dashes).')
  const seen = new Set<string>()
  for (const row of plan.scope) {
    const format = formatOf(catalog, plan.project, row.format)
    if (!format || !formatRenderable(catalog, format)) {
      problems.push(`Format “${row.format}” is not in the ${project.name} catalog.`)
      continue
    }
    if (seen.has(row.format)) problems.push(`Format “${row.format}” is listed twice.`)
    seen.add(row.format)
    if (!isCount(row.count, MAX_PER_FORMAT)) problems.push(`${format.name}: episodes must be a whole number from 0 to ${MAX_PER_FORMAT}.`)
    else if (hasGames(project) && row.count > 0) {
      if (!row.mix.every((n) => isCount(n, MAX_PER_FORMAT)) || row.mix[0] + row.mix[1] + row.mix[2] !== row.count)
        problems.push(`${format.name}: the difficulty mix must add up to ${row.count}.`)
    }
  }
  if (totalEpisodes(plan) === 0) problems.push('Choose at least one episode.')
  if (hasGames(project)) {
    if (!isCount(plan.spares, MAX_SPARES)) problems.push(`Spares must be a whole number from 0 to ${MAX_SPARES}.`)
    for (const game of plannedGames(catalog, plan)) {
      const style = plan.styles[game]
      if (!style || !stylesFor(catalog, game).some((s) => s.id === style)) problems.push(`Choose a style for ${game}.`)
    }
    for (const row of plan.scope.filter((r) => r.count > 0 && formatOf(catalog, plan.project, r.format))) {
      const choice = plan.music[row.format]
      if (choice !== CALM && !bedsFor(catalog, plan.project, row.format).some((b) => b.id === choice))
        problems.push(`Music for ${row.format}: choose the calm rotation or a bed of the right game and length.`)
    }
  } else {
    if (plan.pilots) problems.push(`${project.name} has no pilot step.`)
    if (lines(plan.subjects).length === 0) problems.push('Name at least one subject (a title or story idea per line).')
  }
  if (plan.experimentId && !EXPERIMENT_ID.test(plan.experimentId)) problems.push('Experiment id: lowercase letters, digits and dashes (up to 64).')
  for (const [label, text] of [['Goal', plan.goal], ['Prefer', plan.prefer], ['Avoid', plan.avoid], ['Subjects', plan.subjects], ['Notes', plan.notes]] as const)
    if (text.length > TEXT_LIMIT) problems.push(`${label} is longer than ${TEXT_LIMIT} characters.`)
  return problems
}

function difficultyText(mix: DifficultyMix): string {
  return DIFFICULTY_NAMES.map((name, i) => `${name} ${mix[i]}`).join(', ')
}

function musicText(catalog: Catalog, plan: BatchPlan, format: string): string {
  const choice = plan.music[format] ?? CALM
  if (choice === CALM) return 'calm rotation'
  const bed = bedsFor(catalog, plan.project, format).find((b) => b.id === choice)
  return bed ? `${bed.id} (“${bed.title}”${bed.artist ? `, ${bed.artist}` : ''}, ${bed.license})` : choice
}

/** The brief's Mix lines for a Scalargame plan (rows with episodes only). */
export function scalargameMix(catalog: Catalog, plan: BatchPlan): string[] {
  const rows = plan.scope.filter((r) => r.count > 0)
  const out = [`- Episodes: ${totalEpisodes(plan)} main, plus ${plan.spares} spare${plan.spares === 1 ? '' : 's'} per format`]
  for (const row of rows) {
    const format = formatOf(catalog, plan.project, row.format)
    out.push(`- ${format?.game ?? '?'} / ${row.format}: ${row.count} (${difficultyText(row.mix)})`)
  }
  out.push(plan.pilots ? '- Pilots first: yes, one per game, then Checkpoint 2' : '- Pilots first: no, render the whole batch')
  out.push(`- Styles: ${plannedGames(catalog, plan).map((g) => `${g} → ${plan.styles[g] ?? '?'}`).join('; ')}`)
  out.push(`- Music: ${rows.map((r) => `${r.format} → ${musicText(catalog, plan, r.format)}`).join('; ')}`)
  if (oneLine(plan.prefer)) out.push(`- Prefer: ${oneLine(plan.prefer)}`)
  if (oneLine(plan.avoid)) out.push(`- Avoid: ${oneLine(plan.avoid)}`)
  return out
}

function experimentLines(plan: BatchPlan): string[] {
  const out: string[] = []
  if (plan.experimentId) out.push(`- Experiment ID: ${plan.experimentId}`)
  for (const l of lines(plan.notes)) out.push(`- ${l}`)
  return out
}

/** The brief text the owner can still edit before copying. */
export function buildPlanBrief(catalog: Catalog, plan: BatchPlan, info: Pick<NextBatchInfo, 'openFeedback' | 'lastRetro'> | null): string {
  const project = projectOf(catalog, plan.project)
  if (project && hasGames(project)) {
    const feedback = info ?? { openFeedback: [], lastRetro: null }
    return buildBriefTemplate(
      { nextBatchId: plan.batchId, openFeedback: feedback.openFeedback, lastRetro: feedback.lastRetro },
      { goals: oneLine(plan.goal) ? [`- ${oneLine(plan.goal)}`] : [], mix: scalargameMix(catalog, plan), experiments: experimentLines(plan) },
    )
  }
  const name = project?.name ?? plan.project
  const rows = plan.scope.filter((r) => r.count > 0)
  const engineName = (format: string) => {
    const f = formatOf(catalog, plan.project, format)
    const engine = f ? engineOf(catalog, f.engine) : null
    return f ? `${engine?.name ?? f.engine}${f.route ? ` · ${f.route}` : ''}` : '?'
  }
  const budget = project?.budget
  return [
    `# Brief: ${plan.batchId} (${name})`,
    '',
    `Batch id: ${plan.batchId}`,
    '',
    '## Goals',
    oneLine(plan.goal) ? `- ${oneLine(plan.goal)}` : '- <what this batch should achieve>',
    '',
    '## Mix',
    `- Episodes: ${totalEpisodes(plan)}`,
    ...rows.map((r) => `- ${r.format} (${engineName(r.format)}): ${r.count}`),
    '',
    '## Subjects',
    ...lines(plan.subjects).map((l) => `- ${l}`),
    '',
    '## Budget',
    budget
      ? `- Monthly budget: $${budget.monthlyUsd}${budget.perRunApproval ? '; every paid run needs my OK for that run, with a cost estimate' : ''}.`
      : '- <budget>',
    '',
    '## Checks',
    `- ${(project?.checks ?? []).map((c) => c.name).join(', ') || '<checks>'}`,
    ...(oneLine(plan.prefer) ? ['', '## Prefer', `- ${oneLine(plan.prefer)}`] : []),
    ...(oneLine(plan.avoid) ? ['', '## Avoid', `- ${oneLine(plan.avoid)}`] : []),
    '',
    '## Experiments',
    ...(experimentLines(plan).length ? experimentLines(plan) : ['- <one thing to try>']),
    '',
  ].join('\n')
}

/** The prompt for Claude Code in the StudioZero repo. */
export function buildPlanPrompt(catalog: Catalog, plan: BatchPlan, brief: string): string {
  const project = projectOf(catalog, plan.project)
  if (project && hasGames(project)) return buildCopyPrompt(plan.batchId, brief)
  return [
    `Originals batch ${plan.batchId} for project ${plan.project}.`,
    '',
    'Follow the originals playbook: brief → make with the story engine (engines/story, headless CLI; docs/HEADLESS.md) → check (rights, script sanity, visual QA, AI disclosure) → package → stop at each owner checkpoint → finalize only on my approval.',
    'Before any paid step, show me a cost estimate and wait for my OK for that run. If an open story-engine bug that blocks paid runs applies (docs/STUDIO_PLAN.md), stop and tell me.',
    '',
    brief.trimEnd(),
    '',
    SAFETY_LINES.join('\n'),
  ].join('\n')
}

/** The Mix placeholder for the classic brief (Library feedback flow) from the catalog. */
export function catalogPlaceholderMix(catalog: Catalog, projectId: string): string[] {
  return placeholderMix(catalogGames(catalog), catalogFormats(catalog, projectId))
}

// ---------------------------------------------------------------------------
// Presets: browser-local only (localStorage), wrapped in try/catch; re-checked against the catalog on use.
// ---------------------------------------------------------------------------

export const PRESETS_KEY = 'studio-prompt-presets'
export const MAX_PRESETS = 20
const NAME_LIMIT = 60

export interface PlanPreset {
  name: string
  plan: Omit<BatchPlan, 'batchId'>
}

function safeLocal(): Storage | null {
  try {
    return typeof window === 'undefined' ? null : window.localStorage
  } catch {
    return null
  }
}

function isRecordOfStrings(value: unknown): value is Record<string, string> {
  return typeof value === 'object' && value !== null && !Array.isArray(value) && Object.values(value).every((v) => typeof v === 'string')
}

function parsePreset(value: unknown): PlanPreset | null {
  if (typeof value !== 'object' || value === null) return null
  const { name, plan } = value as { name?: unknown; plan?: Record<string, unknown> }
  if (typeof name !== 'string' || !name.trim() || name.length > NAME_LIMIT || typeof plan !== 'object' || plan === null) return null
  const text = (key: string) => (typeof plan[key] === 'string' ? (plan[key] as string).slice(0, TEXT_LIMIT) : '')
  if (typeof plan.project !== 'string' || !Array.isArray(plan.scope)) return null
  const scope: ScopeRow[] = []
  for (const row of plan.scope as unknown[]) {
    const r = row as { format?: unknown; count?: unknown; mix?: unknown }
    if (typeof r?.format !== 'string' || !isCount(r.count, MAX_PER_FORMAT)) continue
    const mix = Array.isArray(r.mix) && r.mix.length === 3 && r.mix.every((n) => isCount(n, MAX_PER_FORMAT)) ? (r.mix as DifficultyMix) : evenMix(r.count)
    scope.push({ format: r.format, count: r.count, mix: [mix[0], mix[1], mix[2]] })
  }
  return {
    name: name.trim(),
    plan: {
      project: plan.project,
      goal: text('goal'),
      scope,
      spares: isCount(plan.spares, MAX_SPARES) ? plan.spares : 0,
      pilots: plan.pilots === true,
      styles: isRecordOfStrings(plan.styles) ? { ...plan.styles } : {},
      music: isRecordOfStrings(plan.music) ? { ...plan.music } : {},
      experimentId: text('experimentId'),
      prefer: text('prefer'),
      avoid: text('avoid'),
      subjects: text('subjects'),
      notes: text('notes'),
    },
  }
}

export function readPresets(storage: Storage | null = safeLocal()): PlanPreset[] {
  try {
    const raw = storage?.getItem(PRESETS_KEY)
    const data: unknown = raw ? JSON.parse(raw) : []
    return Array.isArray(data) ? data.map(parsePreset).filter((p): p is PlanPreset => p !== null).slice(0, MAX_PRESETS) : []
  } catch {
    return []
  }
}

function writePresets(presets: PlanPreset[], storage: Storage | null): boolean {
  try {
    if (!storage) return false
    storage.setItem(PRESETS_KEY, JSON.stringify(presets))
    return true
  } catch {
    return false
  }
}

/** Save (or replace by name) a preset; the newest comes first. False when storage is blocked or full. */
export function savePreset(name: string, plan: BatchPlan, storage: Storage | null = safeLocal()): boolean {
  const clean = oneLine(name).slice(0, NAME_LIMIT)
  if (!clean) return false
  const { batchId: _drop, ...rest } = plan
  void _drop
  const preset = parsePreset({ name: clean, plan: rest })
  if (!preset) return false
  const others = readPresets(storage).filter((p) => p.name !== clean)
  return writePresets([preset, ...others].slice(0, MAX_PRESETS), storage)
}

export function deletePreset(name: string, storage: Storage | null = safeLocal()): boolean {
  return writePresets(
    readPresets(storage).filter((p) => p.name !== name),
    storage,
  )
}

/**
 * A preset turned back into a plan for `batchId`, keeping only what the catalog still offers: unknown formats are
 * dropped, styles and beds that no longer exist fall back to the defaults.
 */
export function applyPreset(catalog: Catalog, preset: PlanPreset, batchId: string): BatchPlan | null {
  if (!projectOf(catalog, preset.plan.project)) return null
  const base = defaultPlan(catalog, preset.plan.project, batchId)
  const saved = new Map(preset.plan.scope.map((r) => [r.format, r]))
  const scope = base.scope.map((row) => {
    const s = saved.get(row.format)
    return s ? { format: row.format, count: s.count, mix: s.mix } : { ...row, count: 0, mix: evenMix(0) }
  })
  const styles = { ...base.styles }
  for (const [game, style] of Object.entries(preset.plan.styles)) if (stylesFor(catalog, game).some((s) => s.id === style)) styles[game] = style
  const music = { ...base.music }
  for (const [format, bed] of Object.entries(preset.plan.music))
    if (format in music && (bed === CALM || bedsFor(catalog, preset.plan.project, format).some((b) => b.id === bed))) music[format] = bed
  return { ...base, ...preset.plan, batchId, scope, styles, music }
}
