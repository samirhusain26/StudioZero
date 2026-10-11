/**
 * The bundled owner guide (REBUILD_CONTRACTS.md §4): publisher/ui/content/guide/*.md plus meta.json,
 * inlined at build time (never fetched at runtime).
 */
import { assignAnchors, parseMarkdown, type Block } from './markdown'

export interface GuideMeta {
  updated: string
  order: string[]
  /** Screen → anchor the header help icon opens (docs/PI_UI_REDESIGN_PLAN.md §4.6). */
  screens: Record<string, string>
}

export interface GuideDoc {
  /** File name without `.md`, e.g. `upload`. */
  name: string
  blocks: Block[]
}

export interface GuideHeading {
  doc: string
  level: 1 | 2 | 3
  text: string
  anchor: string
}

export interface Guide {
  meta: GuideMeta
  docs: GuideDoc[]
  headings: GuideHeading[]
}

const sources = import.meta.glob('../../content/guide/*.md', { query: '?raw', import: 'default', eager: true }) as Record<string, string>
const metaSources = import.meta.glob('../../content/guide/meta.json', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

function baseName(path: string): string {
  return (path.split('/').pop() ?? path).replace(/\.md$/, '')
}

function parseMeta(raw: string | undefined, names: string[]): GuideMeta {
  try {
    const data = JSON.parse(raw ?? '{}') as { updated?: unknown; order?: unknown; screens?: unknown }
    const order = Array.isArray(data.order) ? data.order.filter((x): x is string => typeof x === 'string') : []
    const screens =
      data.screens && typeof data.screens === 'object'
        ? Object.fromEntries(Object.entries(data.screens).filter((e): e is [string, string] => typeof e[1] === 'string'))
        : {}
    return { updated: typeof data.updated === 'string' ? data.updated : 'unknown', order: order.length ? order : names, screens }
  } catch {
    return { updated: 'unknown', order: names, screens: {} }
  }
}

/** Build the guide from raw files: docs in meta.order (unlisted files follow alphabetically), unique anchors. */
export function buildGuide(files: Record<string, string>, metaRaw: string | undefined): Guide {
  const byName = new Map(Object.entries(files).map(([path, text]) => [baseName(path), text]))
  const names = [...byName.keys()].sort()
  const meta = parseMeta(metaRaw, names)
  const ordered = [...meta.order.filter((n) => byName.has(n)), ...names.filter((n) => !meta.order.includes(n))]
  const parsed = assignAnchors(ordered.map((n) => parseMarkdown(byName.get(n) ?? '')))
  const docs = ordered.map((name, i) => ({ name, blocks: parsed[i] ?? [] }))
  const headings: GuideHeading[] = docs.flatMap((d) =>
    d.blocks.flatMap((b) => (b.type === 'heading' ? [{ doc: d.name, level: b.level, text: b.text, anchor: b.anchor }] : [])),
  )
  return { meta, docs, headings }
}

export const GUIDE: Guide = buildGuide(sources, Object.values(metaSources)[0])

export function hasAnchor(guide: Guide, anchor: string): boolean {
  return guide.headings.some((h) => h.anchor === anchor)
}
