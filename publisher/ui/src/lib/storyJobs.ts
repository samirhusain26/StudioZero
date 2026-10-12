/**
 * Studio › Story jobs: the story worker's projects, runs and settings (docs/STUDIO_PLAN.md §6; parity list
 * docs/plan/STORY_ENGINE_REVIEW.md F1–F26). Pure. The worker (engines/story/src/agent.py) holds every key, estimate and
 * budget check; this only shapes its answers for the screens.
 */
import type {
  StoryEvent,
  StoryPipelineState,
  StoryProject,
  StoryProjectDetail,
  StorySettings,
  StoryStatus,
  StoryStepName,
  StoryStepState,
} from '../api/types'
import type { Tone } from './labels'

/** Pre-production, once per series. */
export const SERIES_STEPS: readonly StoryStepName[] = ['writer', 'screenwriter', 'casting', 'world_builder']
/** Per episode, in run order (set_designer included: review B7). */
export const EPISODE_STEPS: readonly StoryStepName[] = ['director', 'set_designer', 'scene_generator', 'editor']

export const STEP_LABELS: Record<StoryStepName, string> = {
  writer: 'Writer',
  screenwriter: 'Screenwriter',
  casting: 'Casting',
  world_builder: 'World builder',
  director: 'Director',
  set_designer: 'Set designer',
  scene_generator: 'Scene generator',
  editor: 'Editor',
}

const STATUS: Record<StoryStatus, { label: string; tone: Tone }> = {
  created: { label: 'Not started', tone: 'neutral' },
  running: { label: 'Running', tone: 'info' },
  paused: { label: 'Paused', tone: 'neutral' },
  review: { label: 'Script ready for review', tone: 'warn' },
  scene_failed: { label: 'A scene failed', tone: 'warn' },
  error: { label: 'Stopped with an error', tone: 'bad' },
  completed: { label: 'Completed', tone: 'good' },
}

export function statusBadge(status: StoryStatus, running = false): { label: string; tone: Tone } {
  if (running) return STATUS.running
  return STATUS[status] ?? { label: status, tone: 'neutral' }
}

export function routeLabel(route: string): string {
  return route === 'series' ? 'Animation series' : route === 'recap' ? 'Recap' : route
}

export type StepPhase = 'pending' | 'running' | 'done' | 'error'

export interface RailStep {
  name: StoryStepName
  label: string
  phase: StepPhase
  seconds: number | null
  error: string | null
  artifacts: number
  /** null for pre-production steps. */
  episode: number | null
}

export interface RailEpisode {
  episode: number
  phase: StepPhase
  steps: RailStep[]
}

function seconds(from: string | null, to: string | null): number | null {
  if (!from || !to) return null
  const ms = Date.parse(to) - Date.parse(from)
  return Number.isFinite(ms) && ms >= 0 ? Math.round(ms / 1000) : null
}

function railStep(name: StoryStepName, node: StoryStepState | undefined, episode: number | null, running: boolean): RailStep {
  let phase: StepPhase = 'pending'
  if (node?.completed) phase = 'done'
  else if (node?.error) phase = 'error'
  else if (node?.startedAt && running) phase = 'running'
  return {
    name,
    label: STEP_LABELS[name],
    phase,
    seconds: node?.completed ? seconds(node.startedAt, node.completedAt) : null,
    error: node?.error ?? null,
    artifacts: node?.artifacts ?? 0,
    episode,
  }
}

function summary(steps: RailStep[]): StepPhase {
  if (steps.some((s) => s.phase === 'error')) return 'error'
  if (steps.some((s) => s.phase === 'running')) return 'running'
  if (steps.length > 0 && steps.every((s) => s.phase === 'done')) return 'done'
  return 'pending'
}

/** F9: the series step rail from the worker's pipeline state (a missing state = nothing has run). */
export function stepRail(state: StoryPipelineState | null, episodes: number, running: boolean): { preProduction: RailStep[]; episodes: RailEpisode[] } {
  const preProduction = SERIES_STEPS.map((name) => railStep(name, state?.seriesSteps[name], null, running))
  const count = Math.max(episodes, ...Object.keys(state?.episodes ?? {}).map(Number).filter(Number.isFinite), 0)
  const out: RailEpisode[] = []
  for (let ep = 1; ep <= count; ep++) {
    const nodes = state?.episodes[String(ep)]
    const steps = EPISODE_STEPS.map((name) => railStep(name, nodes?.[name], ep, running))
    out.push({ episode: ep, phase: summary(steps), steps })
  }
  return { preProduction, episodes: out }
}

export interface ProjectInfo {
  stepsDone: number
  stepsTotal: number
  totalSeconds: number
  clips: number
  files: number
}

/** F11: progress, time and output counts (series), from the pipeline state. */
export function projectInfo(project: StoryProjectDetail): ProjectInfo {
  const rail = stepRail(project.pipelineState, project.params.num_episodes ?? 1, project.running)
  const all = [...rail.preProduction, ...rail.episodes.flatMap((e) => e.steps)]
  return {
    stepsDone: all.filter((s) => s.phase === 'done').length,
    stepsTotal: all.length,
    totalSeconds: all.reduce((sum, s) => sum + (s.seconds ?? 0), 0),
    clips: all.filter((s) => s.name === 'scene_generator').reduce((sum, s) => sum + s.artifacts, 0),
    files: all.reduce((sum, s) => sum + s.artifacts, 0),
  }
}

export interface BudgetView {
  spentUsd: number
  maxUsd: number
  remainingUsd: number
  percent: number
  over: boolean
}

/** F12: spend from the project's ledger against its budget. */
export function budgetView(spentUsd: number, maxUsd: number): BudgetView {
  const percent = maxUsd > 0 ? Math.min(100, Math.round((spentUsd / maxUsd) * 100)) : spentUsd > 0 ? 100 : 0
  return { spentUsd, maxUsd, remainingUsd: Math.max(0, maxUsd - spentUsd), percent, over: spentUsd > maxUsd }
}

export function usd(value: number): string {
  return `$${value.toFixed(value !== 0 && Math.abs(value) < 1 ? 3 : 2)}`
}

export type LogFilter = 'all' | 'steps' | 'errors'

/** F8: the log filters. Polling and cost lines count as steps. */
export function filterEvents(events: readonly StoryEvent[], filter: LogFilter): StoryEvent[] {
  if (filter === 'errors') return events.filter((e) => e.kind === 'error')
  if (filter === 'steps') return events.filter((e) => e.kind !== 'status')
  return [...events]
}

/** Appends newly polled events (by seq, no duplicates), keeping the last `max`. */
export function mergeEvents(previous: readonly StoryEvent[], next: readonly StoryEvent[], max = 2000): StoryEvent[] {
  const last = previous.length > 0 ? (previous[previous.length - 1]?.seq ?? 0) : 0
  const merged = [...previous, ...next.filter((e) => e.seq > last)]
  return merged.length > max ? merged.slice(merged.length - max) : merged
}

/** The text of one log line: the message, or a description of a polling/cost update. */
export function eventText(event: StoryEvent): string {
  const d = event.data ?? {}
  if (event.kind === 'veo_polling') return `Scene ${String(d.scene_id ?? '?')}: waiting for ${String(d.model ?? 'the video model')} · ${elapsedText(Number(d.elapsed ?? 0))}`
  if (event.kind === 'cost_update') return `Scene ${String(d.scene_id ?? '?')} rendered with ${String(d.model_name ?? 'the video model')} · ${usd(Number(d.scene_cost ?? 0))}`
  return event.message
}

export function elapsedText(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds))
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

/** F16: the video model being waited on, while it is the latest thing that happened. */
export function pollingNote(events: readonly StoryEvent[], running: boolean): string | null {
  if (!running) return null
  const latest = events[events.length - 1]
  return latest?.kind === 'veo_polling' ? eventText(latest) : null
}

/** F8: "Last update 12s ago". */
export function lastUpdateText(events: readonly StoryEvent[], now: number): string | null {
  const latest = events[events.length - 1]
  if (!latest) return null
  const at = Date.parse(latest.at)
  return Number.isFinite(at) ? `Last update ${elapsedText((now - at) / 1000)} ago` : null
}

export type RunAction = { kind: 'run'; label: string } | { kind: 'none'; reason: string }

/** F7/F18: what the run button does now. A review or a failed scene needs a decision first. */
export function runAction(project: StoryProject): RunAction {
  if (project.running) return { kind: 'none', reason: 'Running now.' }
  switch (project.status) {
    case 'created':
      return { kind: 'run', label: 'Start' }
    case 'paused':
      return { kind: 'run', label: 'Continue' }
    case 'error':
      return { kind: 'run', label: 'Retry' }
    case 'review':
      return { kind: 'none', reason: 'Approve the script first.' }
    case 'scene_failed':
      return { kind: 'none', reason: 'Choose what to do with the failed scene first.' }
    case 'completed':
      return { kind: 'none', reason: 'This project is complete.' }
    default:
      return { kind: 'run', label: 'Continue' }
  }
}

/** How often a project page polls: fast while it runs, slowly otherwise (the laptop may be asleep). */
export function pollMs(running: boolean): number {
  return running ? 2000 : 15000
}

/** F20: the preset the current models match, or "custom". */
export function detectPreset(settings: StorySettings): string {
  for (const [id, p] of Object.entries(settings.presets)) {
    if (
      p.llm_model === settings.models.llm_model &&
      p.image_model === settings.models.image_model &&
      p.tts_model === settings.models.tts_model &&
      p.tier === settings.video.active_tier
    )
      return id
  }
  return 'custom'
}

export const TIER_LABELS: Record<string, string> = { cheapest: 'Budget', recommended: 'Recommended', high_fidelity: 'Premium' }

/** F13: the active quality tier and model, e.g. "Recommended · Veo 3.1 Fast". */
export function tierBadge(settings: StorySettings, modelId?: string): string {
  const id = modelId ?? settings.video.active_model
  const model = Object.values(settings.tiers)
    .flat()
    .find((m) => m?.id === id)
  const tier = Object.entries(settings.tiers).find(([, models]) => models?.some((m) => m.id === id))?.[0] ?? settings.video.active_tier
  return `${TIER_LABELS[tier] ?? tier} · ${model?.name ?? id}`
}

export function wordCount(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0
}

/** F14: the edited script as JSON (an object), or why it is not. The worker validates its shape. */
export function parseScript(text: string): { script: Record<string, unknown> } | { error: string } {
  let value: unknown
  try {
    value = JSON.parse(text)
  } catch (e) {
    return { error: `Not valid JSON: ${e instanceof Error ? e.message : 'parse error'}` }
  }
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return { error: 'The script must be a JSON object.' }
  return { script: value as Record<string, unknown> }
}

/** F3/F5: the create form's problems (the worker re-checks). */
export function createProblems(form: { route: 'recap' | 'series'; name: string; brief: string; episodes: number }): string[] {
  const out: string[] = []
  if (!form.name.trim()) out.push(form.route === 'recap' ? 'Type a movie name or a story idea.' : 'Name the series.')
  if (form.name.length > 120) out.push('Keep the name under 120 characters.')
  if (form.route === 'series') {
    if (!form.brief.trim()) out.push('A series needs a brief.')
    if (form.brief.length > 2000) out.push('Keep the brief under 2,000 characters.')
    if (!Number.isInteger(form.episodes) || form.episodes < 1 || form.episodes > 10) out.push('Episodes: 1 to 10.')
  }
  return out
}

/** Hash routes of the Story jobs screens. */
export function jobHash(id: string): string {
  return `#/studio/jobs/${encodeURIComponent(id)}`
}
