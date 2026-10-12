/**
 * Lookups over the studio catalog (`GET /api/catalog`, publisher/catalog.json). Pure functions: every option the
 * Studio offers comes from here, so the UI never offers something an engine cannot render.
 */
import type { Catalog, CatalogBed, CatalogEngine, CatalogFormat, CatalogProject, CatalogStyle, CatalogTemplate } from '../api/types'

export function projectOf(catalog: Catalog, projectId: string): CatalogProject | null {
  return catalog.projects.find((p) => p.id === projectId) ?? null
}

export function engineOf(catalog: Catalog, engineId: string): CatalogEngine | null {
  return catalog.engines.find((e) => e.id === engineId) ?? null
}

/** Projects in catalog order (P0 first). */
export function projectsInOrder(catalog: Catalog): CatalogProject[] {
  return [...catalog.projects].sort((a, b) => a.order - b.order)
}

/** Game ids across projects, in catalog order (what `GAMES` used to hardcode). */
export function catalogGames(catalog: Catalog): string[] {
  const out: string[] = []
  for (const project of catalog.projects) for (const game of project.games ?? []) if (!out.includes(game.id)) out.push(game.id)
  return out
}

/** Format ids of one project, or of every project (what `FORMATS` used to hardcode). */
export function catalogFormats(catalog: Catalog, projectId?: string): string[] {
  const projects = projectId ? catalog.projects.filter((p) => p.id === projectId) : catalog.projects
  return projects.flatMap((p) => p.formats.map((f) => f.id))
}

export function formatOf(catalog: Catalog, projectId: string, formatId: string): CatalogFormat | null {
  return projectOf(catalog, projectId)?.formats.find((f) => f.id === formatId) ?? null
}

export function templateOf(catalog: Catalog, formatId: string): CatalogTemplate | null {
  for (const engine of catalog.engines) {
    const template = engine.templates?.find((t) => t.format === formatId)
    if (template) return template
  }
  return null
}

/** The styles an engine has for one game (Scalargame's recipes). */
export function stylesFor(catalog: Catalog, game: string): CatalogStyle[] {
  return catalog.engines.flatMap((e) => e.styles ?? []).filter((s) => s.game === game)
}

/** Live beds that fit a format: same game, same length as its template. Retired beds are never offered. */
export function bedsFor(catalog: Catalog, projectId: string, formatId: string): CatalogBed[] {
  const format = formatOf(catalog, projectId, formatId)
  const template = templateOf(catalog, formatId)
  if (!format?.game || !template) return []
  return catalog.engines
    .flatMap((e) => e.beds ?? [])
    .filter((b) => !b.retired && b.game === format.game && b.durationSeconds === template.durationSeconds)
}

/** A format the engine can make: motion needs a template, story needs a route that lists the format. */
export function formatRenderable(catalog: Catalog, format: CatalogFormat): boolean {
  const engine = engineOf(catalog, format.engine)
  if (!engine) return false
  if (format.route) return engine.routes.some((r) => r.id === format.route && r.formats.includes(format.id))
  return Boolean(engine.templates?.some((t) => t.format === format.id))
}
