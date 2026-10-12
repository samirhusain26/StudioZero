/**
 * Packaging in the browser with the same code as the Mac (tools/package-core.mjs, projects/scalargame/package-core.mjs,
 * engines/motion/pipeline/render-json-core.mjs): render.json per exported episode, then batch.json (the contract
 * version in the bundle's project.json; v2 stamps each episode with the sha256 of its render.json text).
 * The caller supplies the measured files and the stamp.
 */
import { motionRenderJsonCore, renderJsonText } from '@studio/engines/motion/pipeline/render-json-core.mjs'
import { scalargameEpisodes } from '@studio/projects/scalargame/package-core.mjs'
import { batchDocument, renderErrors } from '@studio/tools/package-core.mjs'
import { coverFrame, type JobBundle, type JobInput } from './bundle'

export interface ExportedFiles {
  createdAt: string
  video: { sha256: string; bytes: number; durationSeconds: number; width: number; height: number; fps: string; videoCodec: string; audioCodec: string }
  cover: { sha256: string; bytes: number }
}

/** render.json for one browser export (tools/RENDER_JSON.md; job.renderer "web"). */
export function webRenderJson(bundle: JobBundle, job: JobInput, files: ExportedFiles, bundleCommit: string): Record<string, unknown> {
  const bedId = job.props.music.bed.replace(/\.m4a$/, '')
  return motionRenderJsonCore({
    input: job,
    createdAt: files.createdAt,
    job: { coverFrame: coverFrame(job), renderer: 'web', bundleCommit },
    video: files.video,
    cover: files.cover,
    bed: bundle.beds[bedId],
    bedId,
    fonts: bundle.fonts[job.styleId] ?? [],
  })
}

/** sha256 of the render.json text the Mac writes for the same document (renderJsonText). */
export async function renderSha256(render: Record<string, unknown>): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(renderJsonText(render)))
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('')
}

/** batch.json text for the bundle's batch from every episode's render.json (sorted by episode id). */
export async function packageWebBatch(bundle: JobBundle, renders: Record<string, unknown>[], stamp: { createdAt: string; commit: string }): Promise<string> {
  const project = bundle.projectManifest
  const studio = bundle.studio as { projects: { id: string }[] }
  const known = new Set(studio.projects.map((p) => p.id))
  const sorted = [...renders].sort((a, b) => String(a.episodeId).localeCompare(String(b.episodeId)))
  const missing = bundle.jobs.map((j) => j.episodeId).filter((id) => !sorted.some((r) => r.episodeId === id))
  if (missing.length) throw new Error(`Not exported yet: ${missing.join(', ')}.`)
  for (const render of sorted) {
    const errors = renderErrors(render, { folder: String(render.episodeId), project, known })
    if (errors.length) throw new Error(`${String(render.episodeId)}/render.json: ${errors.join('; ')}`)
  }
  if (!bundle.set.config.batches.includes(bundle.batchId)) throw new Error(`${bundle.batchId} is not in ${bundle.set.name} CONFIG.batches.`)
  if (!bundle.verification) throw new Error(`No independent source check: ${bundle.verReport} (run the fact-checker first, then make the bundle again).`)
  const renderHashes: Record<string, string> = {}
  for (const render of sorted) renderHashes[String(render.episodeId)] = await renderSha256(render)
  const packaged = scalargameEpisodes({
    renders: sorted,
    project,
    studio,
    config: bundle.set.config,
    setName: bundle.set.name,
    doc: bundle.questions,
    beds: bundle.beds,
    verification: bundle.verification,
    verReport: bundle.verReport,
    recipe: (id) => {
      const recipe = bundle.recipes[id]
      if (!recipe) throw new Error(`No style recipe ${id} in the bundle.`)
      return recipe
    },
    dry: false,
    renderHashes,
  })
  return batchDocument({ project, batchId: bundle.batchId, createdAt: stamp.createdAt, commit: stamp.commit, dirty: false, packaged })
}
