/**
 * Studio › Overview (brief: "Studio section"): projects, engines, budgets, mix and runway from the catalog and
 * the approved schedule. Pure. Budgets and mix targets are the owner's to set: unset values are said, never invented.
 */
import type { Catalog, CatalogProject } from '../api/types'
import { engineOf, formatRenderable, projectsInOrder } from './catalog'
import { addDays, REFILL_DAYS, type Runway } from './runway'

export interface ProjectSummary {
  id: string
  name: string
  priority: string
  summary: string
  formats: { id: string; name: string; engine: string; renderable: boolean }[]
  engines: string[]
  budget: string
  mix: string
  /** Last local day with a live post of this project, null = nothing scheduled, undefined = unknown. */
  scheduledThrough: string | null | undefined
  /** scheduledThrough − REFILL_DAYS: approve the next batch by then so the autopilot's refill finds it. */
  nextBatchBy: string | null | undefined
  contract: string
}

function budgetText(project: CatalogProject): string {
  const { monthlyUsd, perRunApproval } = project.budget
  const parts = [`$${monthlyUsd} a month`]
  if (perRunApproval) parts.push('every paid run needs your OK with a cost estimate')
  else if (monthlyUsd === 0) parts.push('no paid services')
  return parts.join(' · ')
}

function mixText(project: CatalogProject): string {
  const share = `${Math.round(project.mix.share * 100)}% of scheduled posts now`
  return project.mix.target === null ? `${share} · target share not set (your decision)` : `${share} · target ${Math.round(project.mix.target * 100)}%`
}

/** Last scheduled local day of a project: its games' groups (Scalargame), else the group named after the project. */
function projectRunway(project: CatalogProject, runway: Runway | null): string | null {
  if (!runway) return null
  const groups = project.games?.length ? project.games.map((g) => g.id) : [project.id]
  return groups.map((g) => runway.lastDayByGroup[g]).filter((d): d is string => Boolean(d)).sort().at(-1) ?? null
}

/** One summary per project in catalog order, each with its own runway from the approved queue. */
export function projectSummaries(catalog: Catalog, runway: Runway | null | undefined): ProjectSummary[] {
  return projectsInOrder(catalog).map((p) => {
    const through = runway === undefined ? undefined : projectRunway(p, runway)
    const engines = [...new Set(p.formats.map((f) => engineOf(catalog, f.engine)?.name ?? f.engine))]
    return {
      id: p.id,
      name: p.name,
      priority: p.priority,
      summary: p.summary,
      formats: p.formats.map((f) => ({ id: f.id, name: f.name, engine: f.engine, renderable: formatRenderable(catalog, f) })),
      engines,
      budget: budgetText(p),
      mix: mixText(p),
      scheduledThrough: through,
      nextBatchBy: through && /^\d{4}-\d{2}-\d{2}$/.test(through) ? addDays(through, -REFILL_DAYS) : through && null,
      contract: `contract v${p.contractSchemaVersion}`,
    }
  })
}
