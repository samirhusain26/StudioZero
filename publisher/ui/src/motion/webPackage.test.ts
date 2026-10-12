import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { coverFrame, parseBundle, type JobBundle, type JobInput } from './bundle'
import { packageWebBatch, webRenderJson, type ExportedFiles } from './webPackage'

// A bundle like web-jobs.mjs writes, from committed files: the 2026-10 checked questions, the manifests and beds.json.
const repo = (p: string) => resolve(process.cwd(), '../..', p)
const json = (p: string) => JSON.parse(readFileSync(repo(p), 'utf8')) as Record<string, unknown>

function makeBundle(): JobBundle {
  const doc = json('library/_sources/2026-10-06-3921b9e/questions-2026-10.json') as { snapshotId: string; snapshotHash: string; questionsHash: string; questions: Record<string, unknown>[] }
  const beds = json('engines/motion/public/episodes/music/beds.json') as Record<string, Record<string, unknown>>
  const picks = ['continuum-h2h-esp-ken', 'tectonic-missing-pry']
  const questions = doc.questions.filter((q) => picks.includes(String(q.key)))
  const bedFor = { continuum: 'continuum-20-holizna-clouds', tectonic: 'tectonic-22-holizna-new-shoes' } as Record<string, string>
  const jobs: JobInput[] = questions.map((q, i) => {
    const game = String(q.game)
    const bed = bedFor[game] as string
    return {
      episodeId: ['continuum-headtohead-901', 'tectonic-missing-901'][i] as string,
      batchId: '2026-10-webtest',
      revision: 1,
      questionKey: String(q.key),
      questionId: String(q.questionId),
      kitVersion: 'kit-1',
      styleId: game === 'continuum' ? 'continuum-poster-1' : 'tectonic-ocean-1',
      propsHash: 'a'.repeat(64),
      props: { durationInFrames: 600, styleId: '', q: { game, format: String(q.format) }, timing: { infoComplete: 3.5 }, music: { bed: `${bed}.m4a`, volume: 0.8 } },
    }
  })
  return {
    kind: 'studio-motion-jobs',
    version: 1,
    batchId: '2026-10-webtest',
    project: 'scalargame',
    createdAt: '2026-10-12T00:00:00Z',
    repoCommit: 'b'.repeat(40),
    studio: json('studio.json'),
    projectManifest: json('projects/scalargame/project.json') as JobBundle['projectManifest'],
    set: { name: 'questions-webtest', config: { batches: ['2026-10-webtest'], experimentId: 'webtest', variantId: null, reviewer: 'rehearsal' } },
    questions: { snapshotId: doc.snapshotId, snapshotHash: doc.snapshotHash, questionsHash: doc.questionsHash, questions: questions as JobBundle['questions']['questions'] },
    verification: { results: picks.map((key) => ({ key, status: 'pass' })) },
    verReport: 'library/2026-10-pilots/review/source-verification.json',
    recipes: {
      'continuum-poster-1': { styleId: 'continuum-poster-1', game: 'continuum', version: 1, summary: 'poster' },
      'tectonic-ocean-1': { styleId: 'tectonic-ocean-1', game: 'tectonic', version: 1, summary: 'ocean' },
    },
    fonts: { 'continuum-poster-1': ['montserrat', 'plex'], 'tectonic-ocean-1': ['nunito'] },
    beds: Object.fromEntries(Object.values(bedFor).map((b) => [b, beds[b] as JobBundle['beds'][string]])),
    jobs,
  }
}

const files = (n: number): ExportedFiles => ({
  createdAt: '2026-10-12T01:00:00Z',
  video: { sha256: String(n).repeat(64), bytes: 1_400_000, durationSeconds: 20, width: 1080, height: 1920, fps: '30/1', videoCodec: 'h264', audioCodec: 'aac' },
  cover: { sha256: String(n + 1).repeat(64), bytes: 200_000 },
})

describe('job bundle', () => {
  it('accepts a complete bundle and checks the beds against the Pi assets', () => {
    const text = JSON.stringify(makeBundle())
    expect(parseBundle(text).problems).toEqual([])
    const assets = new Set(['episodes/music/continuum-20-holizna-clouds.m4a'])
    expect(parseBundle(text, assets).problems).toEqual(['tectonic-missing-901: music bed tectonic-22-holizna-new-shoes is not on this Pi (retired or local-only).'])
  })

  it('explains what is wrong with other files', () => {
    expect(parseBundle('{').problems).toEqual(['The file is not JSON. Choose review/web-jobs.json from the batch folder.'])
    expect(parseBundle('{"kind":"x"}').problems).toEqual(['This is not a Studio job bundle (web-jobs.json, version 1).'])
    const b = makeBundle()
    const twice = { ...b, jobs: [b.jobs[0], b.jobs[0], { ...b.jobs[1], batchId: 'other', props: {} }] }
    expect(parseBundle(JSON.stringify(twice)).problems).toEqual(['continuum-headtohead-901 appears twice.', 'tectonic-missing-901 belongs to batch other.', 'tectonic-missing-901 has no usable props.'])
  })

  it('picks the cover frame as render.mjs does', () => {
    expect(coverFrame(makeBundle().jobs[0] as JobInput)).toBe(120)
  })
})

describe('browser packaging', () => {
  it('writes render.json with renderer "web" and batch.json with the shared cores', () => {
    const bundle = makeBundle()
    const renders = bundle.jobs.map((job, i) => webRenderJson(bundle, job, files(i + 1), 'c'.repeat(40)))
    expect(renders[0]).toMatchObject({ engine: 'motion', kitVersion: 'kit-1', episodeId: 'continuum-headtohead-901', job: { renderer: 'web', bundleCommit: 'c'.repeat(40), coverFrame: 120 } })
    const body = packageWebBatch(bundle, [...renders].reverse(), { createdAt: '2026-10-12T02:00:00Z', commit: 'c'.repeat(40) })
    const doc = JSON.parse(body) as { schemaVersion: number; batchId: string; generator: Record<string, unknown>; episodes: Record<string, unknown>[] }
    expect(body.endsWith('}\n')).toBe(true)
    expect(doc).toMatchObject({ schemaVersion: 1, batchId: '2026-10-webtest', generator: { repoCommit: 'c'.repeat(40), dirty: false, assetKitVersion: 'kit-1' } })
    expect(doc.episodes.map((e) => [e.episodeId, (e.video as { file: string }).file])).toEqual([
      ['continuum-headtohead-901', 'videos/continuum-headtohead-901.mp4'],
      ['tectonic-missing-901', 'videos/tectonic-missing-901.mp4'],
    ])
    expect((doc.episodes[0] as { experimentId: string }).experimentId).toBe('webtest')
  })

  it('refuses missing exports, a broken render.json and a missing source check', () => {
    const bundle = makeBundle()
    const renders = bundle.jobs.map((job, i) => webRenderJson(bundle, job, files(i + 1), 'c'.repeat(40)))
    const stamp = { createdAt: '2026-10-12T02:00:00Z', commit: 'c'.repeat(40) }
    expect(() => packageWebBatch(bundle, renders.slice(0, 1), stamp)).toThrow('Not exported yet: tectonic-missing-901.')
    expect(() => packageWebBatch(bundle, [renders[0] as Record<string, unknown>, { ...renders[1], costUsd: -1 }], stamp)).toThrow(/costUsd must be a number >= 0/)
    expect(() => packageWebBatch({ ...bundle, verification: null }, renders, stamp)).toThrow(/No independent source check/)
  })
})
