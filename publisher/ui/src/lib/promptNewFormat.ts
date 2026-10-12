/**
 * Studio prompt builder, mode 2: a new format, style or project (brief: "Prompt builder"). Pure functions; the
 * options come from the catalog, the draft lives only in this browser, nothing is written to the Pi.
 *
 * The prompt asks Claude Code to build the template (or route change) plus one pilot, put the pilot where the owner
 * can preview it (Studio › Export's Player for motion, Studio › Story renders for story), and stop for review.
 * Every prompt ends with SAFETY_LINES.
 */
import type { Catalog } from '../api/types'
import { engineOf, formatOf, projectOf, projectsInOrder, stylesFor, templateOf } from './catalog'
import { SAFETY_LINES } from './promptSafety'

export type NewKind = 'format' | 'style' | 'project'

export interface NewFormatPlan {
  kind: NewKind
  /** Existing project (format, style); ignored for a new project. */
  project: string
  /** A new project's display name. */
  projectName: string
  engine: string
  /** Story engine: the route the format uses. */
  route: string
  /** Motion: the game a style (or a Scalargame format) is for. */
  game: string
  /** An existing format to start from ('' = from scratch). */
  baseFormat: string
  /** Working name of the new format or style. */
  name: string
  topic: string
  vocabulary: string[]
  /** In order; a subset of BEATS. */
  beats: string[]
  lengthSeconds: number
  audioMood: string
  constraints: string
}

export const VOCABULARY = [
  'kinetic type',
  'map zooms',
  'counters',
  'reveal stamp',
  'bars that grow from zero',
  'cards dealt in',
  'timeline',
  'side-by-side comparison',
] as const

export const BEATS = ['hook', 'body', 'thinking timer', 'reveal', 'call to action'] as const

export const AUDIO_MOODS = ['calm', 'warm', 'playful', 'tense', 'upbeat', 'no music (sound effects only)'] as const

export const MIN_SECONDS = 8
export const MAX_SECONDS = 90
export const TOPIC_LIMIT = 600
export const CONSTRAINTS_LIMIT = 2000
export const DRAFT_KEY = 'studio-new-format-draft'

/** The id a name becomes: lower case, digits and single hyphens. */
export function slugOf(name: string): string {
  return name
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40)
    .replace(/-+$/, '')
}

export function defaultNewPlan(catalog: Catalog): NewFormatPlan {
  const first = projectsInOrder(catalog)[0]
  const engine = first?.formats[0]?.engine ?? catalog.engines[0]?.id ?? ''
  return {
    kind: 'format',
    project: first?.id ?? '',
    projectName: '',
    engine,
    route: '',
    game: '',
    baseFormat: '',
    name: '',
    topic: '',
    vocabulary: [],
    beats: [...BEATS],
    lengthSeconds: 30,
    audioMood: 'calm',
    constraints: '',
  }
}

function existingIds(catalog: Catalog, kind: NewKind): Set<string> {
  if (kind === 'project') return new Set(catalog.projects.map((p) => p.id))
  if (kind === 'style') return new Set(catalog.engines.flatMap((e) => e.styles ?? []).map((s) => s.id))
  return new Set(catalog.projects.flatMap((p) => p.formats.map((f) => f.id)))
}

/** What blocks the prompt. The engine and options must be ones the catalog has. */
export function newPlanProblems(catalog: Catalog, plan: NewFormatPlan): string[] {
  const out: string[] = []
  const engine = engineOf(catalog, plan.engine)
  const project = plan.kind === 'project' ? null : projectOf(catalog, plan.project)
  const id = slugOf(plan.kind === 'project' ? plan.projectName : plan.name)
  if (!engine) out.push('Choose an engine.')
  if (plan.kind !== 'project' && !project) out.push('Choose a project.')
  if (plan.kind === 'project' && !plan.projectName.trim()) out.push('Name the new project.')
  if (plan.kind !== 'project' && !plan.name.trim()) out.push(plan.kind === 'style' ? 'Name the new style.' : 'Name the new format.')
  if (plan.kind === 'project' && !plan.name.trim()) out.push('Name the new project’s first format.')
  if (id && existingIds(catalog, plan.kind).has(id)) out.push(`“${id}” already exists in the catalog; pick another name.`)
  if (plan.kind === 'style' && engine && !engine.styles?.length) out.push(`The ${engine.name} engine has no styles; a style needs the motion engine.`)
  if (plan.kind === 'style' && !plan.game) out.push('Choose the game the style is for.')
  if (plan.game && project && !(project.games ?? []).some((g) => g.id === plan.game)) out.push('That game is not in this project.')
  if (engine?.routes.length && !engine.routes.some((r) => r.id === plan.route)) out.push(`Choose a ${engine.name} route.`)
  if (plan.baseFormat && (!project || !formatOf(catalog, project.id, plan.baseFormat) || formatOf(catalog, project.id, plan.baseFormat)?.engine !== plan.engine))
    out.push('The format to start from must be one of this project’s formats on the same engine.')
  if (!plan.topic.trim()) out.push('Describe the topic.')
  if (plan.topic.length > TOPIC_LIMIT) out.push(`Keep the topic under ${TOPIC_LIMIT} characters.`)
  if (plan.constraints.length > CONSTRAINTS_LIMIT) out.push(`Keep the constraints under ${CONSTRAINTS_LIMIT} characters.`)
  if (plan.beats.length === 0) out.push('Keep at least one beat in the structure.')
  if (plan.beats.some((b) => !(BEATS as readonly string[]).includes(b))) out.push('Unknown beat.')
  if (plan.vocabulary.some((v) => !(VOCABULARY as readonly string[]).includes(v))) out.push('Unknown visual element.')
  if (!(AUDIO_MOODS as readonly string[]).includes(plan.audioMood)) out.push('Choose an audio mood.')
  if (!Number.isInteger(plan.lengthSeconds) || plan.lengthSeconds < MIN_SECONDS || plan.lengthSeconds > MAX_SECONDS)
    out.push(`Length: ${MIN_SECONDS} to ${MAX_SECONDS} seconds.`)
  return out
}

function oneLine(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}

/** The motion engine's in-browser render limits, so the template previews and exports in Studio as on the Mac. */
const BROWSER_LIMITS =
  'Studio previews and exports motion in the browser (Remotion client-side rendering), so the template must render the same there: no z-index, no repeating or radial CSS gradients, no inset box-shadows, no blend modes, raster-only masks; draw rulings, hatching and vignettes as SVG with explicit pixel width and height (engines/motion/src/projects/scalargame/kit/paint.tsx has helpers), and use @remotion/media <Audio>.'

function motionSteps(projectId: string, id: string, pilot: string): string[] {
  return [
    `1. Build: template code under engines/motion/src/projects/${projectId}/ (the placement rule in AGENTS.md); content, captions and rules in projects/${projectId}/project.json; register it so node tools/export-catalog.mjs lists it and the catalog check passes. ${BROWSER_LIMITS}`,
    '2. Check: (cd engines/motion && ./node_modules/.bin/tsc --noEmit); stills of the key frames with ./node_modules/.bin/remotion still (hook, each beat, reveal, last frame).',
    `3. Pilot: one episode in a scratch batch ${pilot} under library/_dev/ (ignored by git), rendered with render/render.sh and checked like a batch episode (loudness, true peak, sync, silence, black frames; render.json with credits). Then write its Studio job bundle: node engines/motion/pipeline/web-jobs.mjs --batch=${pilot} --set=<the pilot's set> --dir=library/_dev/${pilot}, so I can open it in Studio › Export and watch it in the Player (and export it in the browser to compare).`,
    `4. The Player only knows templates that are in the deployed UI bundle: run (cd publisher/ui && npm run build:static && npm run check:static) and all checks, commit, and ask me before pushing ${id} to main and syncing the Pi.`,
  ]
}

function storySteps(plan: NewFormatPlan, projectId: string, pilot: string): string[] {
  return [
    `1. Build: the ${plan.route} route changes in engines/story (registry.json, steps, prompts); the format, captions and rules in projects/${projectId}/project.json; register it so node tools/export-catalog.mjs lists it under the ${plan.route} route and the catalog check passes.`,
    '2. Check: the $0 smoke test (.venv/bin/python -m unittest discover -s tests -v, every key dummy, sockets blocked) covers the new path.',
    `3. Pilot: ${pilot}. First a $0 dry run (mocked or --offline). A real pilot uses paid services: create it as a Story job in Studio (or headless), show me the worker's cost estimate, and run it only after I confirm that estimate. Its render.json (models, cost, credits, disclosure) puts it in Studio › Story renders for my review.`,
  ]
}

/** The prompt for Claude Code (in the StudioZero repo). */
export function buildNewFormatPrompt(catalog: Catalog, plan: NewFormatPlan, now: Date = new Date()): string {
  const engine = engineOf(catalog, plan.engine)
  const project = plan.kind === 'project' ? null : projectOf(catalog, plan.project)
  const projectId = plan.kind === 'project' ? slugOf(plan.projectName) : (project?.id ?? plan.project)
  const id = slugOf(plan.name)
  const pilot = `${now.toISOString().slice(0, 7)}-pilot-${id || 'new'}`
  const base = plan.baseFormat ? formatOf(catalog, projectId, plan.baseFormat) : null
  const baseTemplate = plan.baseFormat ? templateOf(catalog, plan.baseFormat) : null
  const styles = plan.game ? stylesFor(catalog, plan.game).map((s) => s.id) : []
  const what =
    plan.kind === 'style'
      ? `New style “${oneLine(plan.name)}” (id ${id}) for ${plan.game} in project ${projectId}, on the ${engine?.name ?? plan.engine} engine.`
      : plan.kind === 'project'
        ? `New project “${oneLine(plan.projectName)}” (id ${projectId}) with its first format “${oneLine(plan.name)}” (id ${id}), on the ${engine?.name ?? plan.engine} engine.`
        : `New format “${oneLine(plan.name)}” (id ${id}) for project ${projectId}, on the ${engine?.name ?? plan.engine} engine${plan.route ? ` (${plan.route} route)` : ''}.`
  const lines = [
    what,
    'Build it in this repo and make one pilot for my review. Do not start a batch.',
    '',
    'Spec:',
    `- Topic: ${oneLine(plan.topic)}`,
    ...(plan.game && plan.kind !== 'style' ? [`- Game: ${plan.game}`] : []),
    ...(base ? [`- Start from: ${base.name} (${base.id}${baseTemplate ? `, component ${baseTemplate.component}, ${baseTemplate.durationSeconds} s` : ''})`] : []),
    ...(plan.kind === 'style' && styles.length ? [`- Existing ${plan.game} styles (keep the new one clearly different): ${styles.join(', ')}`] : []),
    `- Visual vocabulary: ${plan.vocabulary.length ? plan.vocabulary.join(', ') : 'your call; keep it simple and readable on a phone'}`,
    `- Structure, in order: ${plan.beats.join(' → ')}`,
    `- Length: about ${plan.lengthSeconds} s, 1080 × 1920, 30 fps`,
    `- Audio mood: ${plan.audioMood}`,
    ...(plan.constraints.trim() ? ['- Constraints:', ...plan.constraints.trim().split('\n').map((l) => `  ${l.trim()}`).filter((l) => l.trim())] : []),
    '',
    'Steps:',
    ...(plan.kind === 'project'
      ? [
          `0. Project: add projects/${projectId}/project.json (formats, sources, link and call-to-action policy, caption defaults, required checks) and list it in studio.json. Budget monthlyUsd 0 with per-run approval and mix target null: both are my decisions. Its batches use contract v2 and need a project module in contract/projects/; ask me before adding one (a contract change).`,
        ]
      : []),
    ...(engine?.id === 'story' ? storySteps(plan, projectId, pilot) : motionSteps(projectId, id, pilot)),
    '',
    'Stop after the pilot and show me: the stills, where the pilot is (Studio › Export bundle or Studio › Story renders), its QA numbers, its credits and anything you were unsure of. Wait for my review before anything else.',
    'The repo is public: commit no media, renders or job bundles, and ask me before committing props that name unposted answers. Run python3 tools/public_safety_check.py before any push.',
    '',
    SAFETY_LINES.join('\n'),
  ]
  return lines.join('\n')
}

// ---------------------------------------------------------------------------
// Draft: browser-local only (localStorage), wrapped in try/catch; re-checked against the catalog on use.
// ---------------------------------------------------------------------------

function safeLocal(): Storage | null {
  try {
    return window.localStorage
  } catch {
    return null
  }
}

export function readDraft(catalog: Catalog, storage: Storage | null = safeLocal()): NewFormatPlan {
  const fallback = defaultNewPlan(catalog)
  try {
    const raw = storage?.getItem(DRAFT_KEY)
    if (!raw) return fallback
    const value = JSON.parse(raw) as Partial<NewFormatPlan>
    const plan: NewFormatPlan = {
      ...fallback,
      ...Object.fromEntries(Object.entries(value).filter(([k, v]) => k in fallback && typeof v === typeof fallback[k as keyof NewFormatPlan])),
    }
    plan.vocabulary = Array.isArray(plan.vocabulary) ? plan.vocabulary.filter((v) => (VOCABULARY as readonly string[]).includes(v)) : []
    plan.beats = Array.isArray(plan.beats) ? BEATS.filter((b) => plan.beats.includes(b)) : [...BEATS]
    if (!engineOf(catalog, plan.engine)) plan.engine = fallback.engine
    if (plan.kind !== 'project' && !projectOf(catalog, plan.project)) plan.project = fallback.project
    return plan
  } catch {
    return fallback
  }
}

export function writeDraft(plan: NewFormatPlan, storage: Storage | null = safeLocal()): boolean {
  try {
    storage?.setItem(DRAFT_KEY, JSON.stringify(plan))
    return Boolean(storage)
  } catch {
    return false
  }
}
