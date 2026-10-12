/**
 * Defensive reading of the imported batch.json episode object (EpisodeDetail.episode is
 * `Record<string, unknown>`): every field may be missing on legacy or manual episodes.
 */

export type Rec = Record<string, unknown>

export function rec(value: unknown): Rec | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Rec) : null
}

export function str(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null
}

export function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
}

export interface ViewChoice {
  key: string
  label: string
}

export interface ViewSource {
  title: string
  url: string | null
  retrieved: string | null
}

export interface EpisodeView {
  episodeId: string | null
  questionId: string | null
  revision: number | null
  game: string | null
  format: string | null
  language: string | null
  difficulty: string | null
  styleId: string | null
  experimentId: string | null
  variantId: string | null
  hook: string | null
  question: string | null
  clues: string[]
  choices: ViewChoice[]
  answer: string | null
  answerAliases: string[]
  explanation: string | null
  sources: ViewSource[]
  checks: [string, unknown][]
  reviewer: string | null
  music: { trackId: string | null; license: string | null; sha256: string | null } | null
  video: Rec | null
  cover: Rec | null
  publication: Rec | null
  eligibility: Rec | null
}

/**
 * Contract v2 keeps the project's fields in projectData: Scalargame's quiz fields (game, difficulty, styleId,
 * creative, evidence, music), Originals' subject, sources, checks and reviewer. Read both versions alike.
 */
export function readEpisode(raw: Rec): EpisodeView {
  const v2 = typeof raw.contentId === 'string'
  const data = v2 ? (rec(raw.projectData) ?? {}) : {}
  const episode: Rec = v2 ? { ...raw, ...data, questionId: raw.contentId } : raw
  const subject = rec(data.subject)
  const creative = rec(episode.creative) ?? (subject ? { hook: str(subject.title), question: str(subject.title) } : {})
  const evidence =
    rec(episode.evidence) ?? (v2 && !rec(data.evidence) ? { sources: data.sources, checks: data.checks, reviewer: data.reviewer } : {})
  const music = rec(episode.music)
  const choices = Array.isArray(creative.choices)
    ? creative.choices.flatMap((c) => {
        const r = rec(c)
        const key = str(r?.key)
        const label = str(r?.label)
        return key && label ? [{ key, label }] : []
      })
    : []
  const sources = Array.isArray(evidence.sources)
    ? evidence.sources.flatMap((s) => {
        const r = rec(s)
        if (!r) return []
        const url = str(r.url)
        return [{ title: str(r.title) ?? url ?? 'Untitled source', url, retrieved: str(r.retrieved) }]
      })
    : []
  return {
    episodeId: str(episode.episodeId),
    questionId: str(episode.questionId),
    revision: num(episode.revision),
    game: str(episode.game),
    format: str(episode.format),
    language: str(episode.language),
    difficulty: str(episode.difficulty),
    styleId: str(episode.styleId),
    experimentId: str(episode.experimentId),
    variantId: str(episode.variantId),
    hook: str(creative.hook),
    question: str(creative.question),
    clues: strings(creative.clues),
    choices,
    answer: str(creative.answer),
    answerAliases: strings(creative.answerAliases),
    explanation: str(creative.explanation),
    sources,
    checks: Object.entries(rec(evidence.checks) ?? {}),
    reviewer: str(evidence.reviewer),
    music: music ? { trackId: str(music.trackId), license: str(music.license), sha256: str(music.sha256) } : null,
    video: rec(episode.video),
    cover: rec(episode.cover),
    publication: rec(episode.publication),
    eligibility: rec(episode.eligibility),
  }
}

const norm = (s: string) => s.trim().toLowerCase()

/** The choice that is the answer: label (or key) equal to the answer or one of its aliases. */
export function correctChoiceKey(view: Pick<EpisodeView, 'choices' | 'answer' | 'answerAliases'>): string | null {
  if (!view.answer) return null
  const accepted = new Set([view.answer, ...view.answerAliases].map(norm))
  const byLabel = view.choices.find((c) => accepted.has(norm(c.label)))
  if (byLabel) return byLabel.key
  return view.choices.find((c) => norm(c.key) === norm(view.answer as string))?.key ?? null
}

/** A check value as short text (objects as compact JSON). */
export function checkText(value: unknown): string {
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (value === null || value === undefined) return '—'
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

/** Only https links are rendered as links. */
export function httpsUrl(url: string | null): string | null {
  if (!url) return null
  try {
    return new URL(url).protocol === 'https:' ? url : null
  } catch {
    return null
  }
}

/** "motion · render.sh", "motion · browser export", "story · recap"; the renderer is not recorded for v1 episodes. */
export function engineText(e: { engine: string; route: string | null; renderer: string | null }): string {
  if (e.engine === 'story') return e.route ? `story · ${e.route}` : 'story'
  if (e.renderer === 'web') return `${e.engine} · browser export`
  return e.renderer ? `${e.engine} · ${e.renderer}` : e.engine
}
