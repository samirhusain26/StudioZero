import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { MotionManifest } from '../../api/types'
import { memoryStore } from '../../motion/store'

const exportEpisode = vi.fn()
vi.mock('../../motion/engine', () => ({
  FPS: 30,
  WIDTH: 1080,
  HEIGHT: 1920,
  checkDevice: vi.fn(),
  loadKit: vi.fn(() => new Promise(() => undefined)),
  exportEpisode: (...args: unknown[]) => exportEpisode(...args) as unknown,
}))
const { ExportContent } = await import('./ExportView')

const manifest: MotionManifest = {
  version: '0123456789abcdef',
  base: '/api/assets/motion/0123456789abcdef',
  files: { 'episodes/music/scalar-24-a.m4a': { bytes: 1, sha256: 'a'.repeat(64) } },
}

const job = (id: string) => ({
  episodeId: id,
  batchId: '2026-10-webtest',
  revision: 1,
  questionKey: `k-${id}`,
  questionId: `scalar:${id}`,
  kitVersion: 'kit-1',
  styleId: 'scalar-notebook-1',
  propsHash: 'b'.repeat(64),
  props: { durationInFrames: 720, styleId: 'scalar-notebook-1', q: { game: 'scalar', format: 'progressive-clues' }, timing: { infoComplete: 7.5 }, music: { bed: 'scalar-24-a.m4a', volume: 0.8 } },
})
const bundle = {
  kind: 'studio-motion-jobs',
  version: 1,
  batchId: '2026-10-webtest',
  project: 'scalargame',
  createdAt: '2026-10-12T03:49:00Z',
  repoCommit: 'c'.repeat(40),
  studio: {},
  projectManifest: { id: 'scalargame' },
  set: { name: 's', config: { batches: ['2026-10-webtest'], experimentId: 'x', variantId: null, reviewer: 'r' } },
  questions: { snapshotId: 's', snapshotHash: 'h', questionsHash: 'q', questions: [] },
  verification: null,
  verReport: 'v',
  recipes: {},
  fonts: { 'scalar-notebook-1': [] },
  beds: { 'scalar-24-a': { bed: 'scalar-24-a' } },
  jobs: [job('scalar-clues-901'), job('scalar-clues-902')],
}
const file = (doc: unknown) => new File([JSON.stringify(doc)], 'web-jobs.json', { type: 'application/json' })

describe('Studio › Export', () => {
  afterEach(() => {
    exportEpisode.mockReset()
  })

  it('opens a bundle, refuses a bad one, and keeps finalizing locked until every episode passed', async () => {
    const user = userEvent.setup()
    const store = memoryStore()
    render(<ExportContent manifest={manifest} store={store} device={{ canExport: true, issues: [] }} commit={'d'.repeat(40)} />)
    await user.upload(screen.getByLabelText('Job bundle (web-jobs.json)'), file({ ...bundle, jobs: [{ ...job('x'), props: { ...job('x').props, music: { bed: 'gone.m4a', volume: 1 } } }] }))
    expect(await screen.findByRole('alert')).toHaveTextContent('x: music bed gone is not in the bundle.')
    await user.upload(screen.getByLabelText('Job bundle (web-jobs.json)'), file(bundle))
    expect(await screen.findByTestId('bundle-summary')).toHaveTextContent('Batch 2026-10-webtest · 2 episodes')
    expect(screen.getAllByTestId('export-row').map((r) => r.textContent)).toEqual([
      expect.stringContaining('scalar-clues-901'),
      expect.stringContaining('scalar-clues-902'),
    ])
    expect(screen.getByRole('button', { name: 'Finalize and upload 2026-10-webtest' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Export all' })).toBeEnabled()
    expect((await store.getBundle())?.batchId).toBe('2026-10-webtest')
  })

  it('exports one episode, keeps it in the store and shows its failed checks', async () => {
    const user = userEvent.setup()
    const store = memoryStore()
    exportEpisode.mockResolvedValue({
      mp4: new Blob(['v']),
      cover: new Blob(['c']),
      files: { createdAt: 'x', video: { bytes: 1_400_000 }, cover: { bytes: 1 } },
      measures: { loudnessLufs: -14, truePeakDbtp: -0.5 },
      errors: ['true peak -0.5 dBTP above −1'],
      master: { lufs: -14, truePeakDbtp: -1.2, ceilingDb: -1.5 },
      primingSamples: 2112,
      seconds: 20,
    })
    render(<ExportContent manifest={manifest} store={store} device={{ canExport: true, issues: [] }} commit={'d'.repeat(40)} />)
    await user.upload(screen.getByLabelText('Job bundle (web-jobs.json)'), file(bundle))
    const row = (await screen.findAllByTestId('export-row'))[0] as HTMLElement
    await user.click(within(row).getByRole('button', { name: 'Export' }))
    await waitFor(() => expect(within(row).getByText('Failed checks')).toBeInTheDocument())
    expect(within(row).getByText('true peak -0.5 dBTP above −1')).toBeInTheDocument()
    expect(exportEpisode).toHaveBeenCalledWith(expect.objectContaining({ episodeId: 'scalar-clues-901' }), expect.objectContaining({ staticBase: manifest.base }))
    expect((await store.getExports('2026-10-webtest')).map((e) => e.episodeId)).toEqual(['scalar-clues-901'])
    expect(screen.getByRole('button', { name: 'Export all' })).toBeEnabled()
  })

  it('says when this browser cannot export, and what to do on a phone', () => {
    render(<ExportContent manifest={manifest} store={memoryStore()} device={{ canExport: false, issues: ['No H.264 encoder'] }} commit={null} />)
    expect(screen.getByRole('alert')).toHaveTextContent('No H.264 encoder')
  })
})
