import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiRequestError, api } from '../../api/client'
import type { StoryEstimate, StoryHealth, StoryProject, StoryProjectDetail, StorySettings } from '../../api/types'
import { StoryJobsView } from './StoryJobsView'
import { StoryJobView } from './StoryJobView'
import { StorySettingsView } from './StorySettingsView'

const health: StoryHealth = { ok: true, version: 'agent-test', engine: 'story', running: [], keys: { gemini: true, fal: false }, paidRunsEnabled: true, originalsBudget: { monthlyUsd: 30 } }

const settings: StorySettings = {
  models: { llm_model: 'gemini-2.5-flash', image_model: 'gemini-2.5-flash-image', tts_model: 'gemini-2.5-flash-preview-tts' },
  choices: { llm_model: ['gemini-2.5-flash-lite', 'gemini-2.5-flash'], image_model: ['gemini-2.5-flash-image'], tts_model: ['gemini-2.5-flash-preview-tts'] },
  video: { active_model: 'veo-3.1-fast', active_tier: 'recommended', max_budget: 10, auto_downgrade: true },
  tiers: {
    cheapest: [{ id: 'veo-3.1-lite', name: 'Veo 3.1 Lite', provider: 'gemini', costPerSecondUsd: 0.05, maxResolution: '720p', maxDurationSeconds: 8, audio: true, referenceImages: false, description: '', episodeUsd: 2.4 }],
    recommended: [{ id: 'veo-3.1-fast', name: 'Veo 3.1 Fast', provider: 'gemini', costPerSecondUsd: 0.15, maxResolution: '1080p', maxDurationSeconds: 8, audio: true, referenceImages: true, description: '', episodeUsd: 7.2 }],
  },
  presets: {
    budget: { llm_model: 'gemini-2.5-flash-lite', image_model: 'gemini-2.5-flash-image', tts_model: 'gemini-2.5-flash-preview-tts', tier: 'cheapest' },
    balanced: { llm_model: 'gemini-2.5-flash', image_model: 'gemini-2.5-flash-image', tts_model: 'gemini-2.5-flash-preview-tts', tier: 'recommended' },
  },
  keys: { gemini: true, fal: false },
}

const project = (over: Partial<StoryProject> = {}): StoryProject => ({
  id: 'Show',
  name: 'Show',
  route: 'series',
  params: { num_episodes: 1, brief: 'Tools in space.' },
  status: 'created',
  running: false,
  currentStep: null,
  createdAt: '2026-10-12T10:00:00Z',
  updatedAt: '2026-10-12T10:00:00Z',
  error: null,
  videoModel: 'veo-3.1-fast',
  spentUsd: 0,
  maxBudgetUsd: 10,
  failedScene: null,
  ...over,
})

const detail = (over: Partial<StoryProjectDetail> = {}): StoryProjectDetail => ({ ...project(), pipelineState: null, ...over })

const estimate: StoryEstimate = {
  estimateUsd: 7.2,
  lines: [{ what: '6 video clip(s) with Veo 3.1 Fast', usd: 7.2 }],
  unpriced: ['Gemini text and image calls'],
  token: 'est-abc1234567',
  spentUsd: 0,
  maxBudgetUsd: 10,
  paidRunsEnabled: true,
  originalsBudget: { monthlyUsd: 30 },
}

describe('Story jobs', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('says "Worker offline" with its next step when the laptop is away', async () => {
    const offline = new ApiRequestError(503, 'Worker offline', 'Wake the laptop that runs the story worker (or start it), then try again.')
    vi.spyOn(api, 'storyHealth').mockRejectedValue(offline)
    vi.spyOn(api, 'storyProjects').mockRejectedValue(offline)
    vi.spyOn(api, 'storySettings').mockRejectedValue(offline)
    render(<StoryJobsView />)
    const card = await screen.findByTestId('story-worker')
    await waitFor(() => expect(card).toHaveTextContent('Worker offline'))
    expect(card).toHaveTextContent('Wake the laptop')
    expect(screen.queryByRole('heading', { name: 'New job' })).not.toBeInTheDocument()
  })

  it('lists jobs, creates a series and confirms deletes (F1, F2, F5)', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'storyHealth').mockResolvedValue(health)
    vi.spyOn(api, 'storyProjects').mockResolvedValue({ projects: [project({ status: 'running', running: true }), project({ id: 'Old', name: 'Old', route: 'recap', params: {}, status: 'completed', updatedAt: '2026-10-11T00:00:00Z' })] })
    vi.spyOn(api, 'storySettings').mockResolvedValue(settings)
    const create = vi.spyOn(api, 'storyCreate').mockResolvedValue(project({ id: 'New' }))
    const remove = vi.spyOn(api, 'storyDelete').mockResolvedValue({ ok: true })
    render(<StoryJobsView />)
    const rows = await screen.findAllByTestId('story-job')
    expect(rows[0]).toHaveTextContent('Running')
    expect(within(rows[0] as HTMLElement).getByRole('button', { name: 'Delete' })).toBeDisabled()
    expect(screen.getByTestId('story-worker')).toHaveTextContent('gemini set · fal missing')

    await user.click(screen.getByRole('radio', { name: /Animation series/ }))
    await user.click(screen.getByRole('button', { name: 'Create job' }))
    expect(screen.getByText('A series needs a brief.')).toBeInTheDocument()
    expect(create).not.toHaveBeenCalled()
    expect(screen.getByText('Recommended · Veo 3.1 Fast')).toBeInTheDocument()
    await user.type(screen.getByLabelText('Series name'), 'New')
    await user.type(screen.getByLabelText('Brief'), 'A brief.')
    await user.click(screen.getByRole('button', { name: 'Create job' }))
    expect(create).toHaveBeenCalledWith({ route: 'series', name: 'New', brief: 'A brief.', episodes: 1 })
    await waitFor(() => expect(window.location.hash).toBe('#/studio/jobs/New'))

    await user.click(within(rows[1] as HTMLElement).getByRole('button', { name: 'Delete' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete Old' }))
    expect(remove).toHaveBeenCalledWith('Old', 'Old')
  })

  it('runs only after the estimate is confirmed, sending the worker its own token (F7)', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'storyProject').mockResolvedValue(detail())
    vi.spyOn(api, 'storyEvents').mockResolvedValue({ events: [], last: 0, running: false, status: 'created' })
    vi.spyOn(api, 'storySettings').mockResolvedValue(settings)
    vi.spyOn(api, 'storyEstimate').mockResolvedValue(estimate)
    const run = vi.spyOn(api, 'storyRun').mockResolvedValue(project({ status: 'running', running: true }))
    render(<StoryJobView id="Show" />)
    await user.click(await screen.findByRole('button', { name: 'Start…' }))
    const dialog = await screen.findByTestId('story-estimate')
    expect(dialog).toHaveTextContent('6 video clip(s) with Veo 3.1 Fast: $7.20')
    expect(dialog).toHaveTextContent('Gemini text and image calls')
    expect(dialog).toHaveTextContent('Originals budget: $30 a month.')
    expect(run).not.toHaveBeenCalled()
    await user.click(within(dialog).getByRole('button', { name: 'Run: $7.20 + unpriced calls' }))
    expect(run).toHaveBeenCalledWith('Show', { token: 'est-abc1234567', estimateUsd: 7.2 })
  })

  it('blocks a run over budget or with paid runs off', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'storyProject').mockResolvedValue(detail({ status: 'paused', spentUsd: 5 }))
    vi.spyOn(api, 'storyEvents').mockResolvedValue({ events: [], last: 0, running: false, status: 'paused' })
    vi.spyOn(api, 'storySettings').mockResolvedValue(settings)
    vi.spyOn(api, 'storyEstimate').mockResolvedValue({ ...estimate, spentUsd: 5, paidRunsEnabled: false })
    render(<StoryJobView id="Show" />)
    await user.click(await screen.findByRole('button', { name: 'Continue…' }))
    const dialog = await screen.findByTestId('story-estimate')
    expect(dialog).toHaveTextContent('would go over the job')
    expect(dialog).toHaveTextContent('Paid runs are switched off')
    expect(within(dialog).getByRole('button', { name: /^Run/ })).toBeDisabled()
  })

  it('reviews a recap script: edit, save and approve (F14)', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'storyProject').mockResolvedValue(detail({ route: 'recap', params: {}, status: 'review', script: { title: 'A' }, scriptApproved: false }))
    vi.spyOn(api, 'storyEvents').mockResolvedValue({ events: [], last: 0, running: false, status: 'review' })
    vi.spyOn(api, 'storySettings').mockResolvedValue(settings)
    const save = vi.spyOn(api, 'storySaveScript').mockResolvedValue(project({ route: 'recap', status: 'review', script: { title: 'B' } }))
    const approve = vi.spyOn(api, 'storyApproveScript').mockResolvedValue(project({ route: 'recap', status: 'paused', script: { title: 'B' }, scriptApproved: true }))
    render(<StoryJobView id="Show" />)
    const box = await screen.findByLabelText('Script (JSON)')
    expect(screen.getByText('Approve the script first.')).toBeInTheDocument()
    await user.clear(box)
    await user.type(box, '{{"title": "B"}')
    await user.click(screen.getByRole('button', { name: 'Save and approve' }))
    expect(save).toHaveBeenCalledWith('Show', { title: 'B' })
    expect(approve).toHaveBeenCalledWith('Show')
  })

  it('decides a failed scene, then shows the new estimate (F15)', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'storyProject').mockResolvedValue(
      detail({ status: 'scene_failed', failedScene: { episode: 1, scene: 3, prompt: 'A wrench flies.', error: 'Safety filter' } }),
    )
    vi.spyOn(api, 'storyEvents').mockResolvedValue({ events: [], last: 0, running: false, status: 'scene_failed' })
    vi.spyOn(api, 'storySettings').mockResolvedValue(settings)
    const scene = vi.spyOn(api, 'storyScene').mockResolvedValue({ ...project({ status: 'paused', videoModel: 'veo-3.1-lite' }), estimate: { ...estimate, estimateUsd: 0.4 } })
    render(<StoryJobView id="Show" />)
    expect(await screen.findByRole('heading', { name: 'Scene 3 of episode 1 failed' })).toBeInTheDocument()
    expect(screen.getByText('Safety filter')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save edits & retry' })).toBeDisabled()
    await user.selectOptions(await screen.findByLabelText('Video model for this job'), 'veo-3.1-lite')
    await user.click(screen.getByRole('button', { name: 'Change model & retry' }))
    expect(scene).toHaveBeenCalledWith('Show', 'change_model', '', 'veo-3.1-lite')
    expect(await screen.findByTestId('story-estimate')).toHaveTextContent('$0.400')
  })

  it('shows the step rail with set designer, cancel while running, polling and the log (F8, F9, F16, F17)', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'storyProject').mockResolvedValue(
      detail({
        status: 'running',
        running: true,
        pipelineState: {
          seriesSteps: { writer: { completed: true, startedAt: '2026-10-12T10:00:00Z', completedAt: '2026-10-12T10:00:20Z', error: null, artifacts: 1 } },
          episodes: { '1': { director: { completed: true, startedAt: '2026-10-12T10:01:00Z', completedAt: '2026-10-12T10:01:30Z', error: null, artifacts: 1 } } },
        },
      }),
    )
    vi.spyOn(api, 'storyEvents').mockResolvedValue({
      events: [
        { seq: 1, at: '2026-10-12T10:00:00Z', kind: 'status', message: 'Run started' },
        { seq: 2, at: '2026-10-12T10:00:01Z', kind: 'error', message: 'quota' },
        { seq: 3, at: '2026-10-12T10:02:00Z', kind: 'veo_polling', message: '', data: { scene_id: 2, elapsed: 30, model: 'veo-3.1-fast' } },
      ],
      last: 3,
      running: true,
      status: 'running',
    })
    vi.spyOn(api, 'storySettings').mockResolvedValue(settings)
    const cancel = vi.spyOn(api, 'storyCancel').mockResolvedValue({ ...project({ status: 'running', running: true }), cancelling: true })
    const artifacts = vi.spyOn(api, 'storyArtifacts').mockResolvedValue({ step: 'director', episode: 1, files: [{ path: 'episodes/episode_1/director_shots.json', bytes: 10, kind: 'json', json: { shots: [{ scene_id: 1, dialogue: 'Incoming!' }] } }] })
    render(<StoryJobView id="Show" />)
    expect(await screen.findByTestId('story-polling')).toHaveTextContent('Scene 2: waiting for veo-3.1-fast · 30s')
    const steps = screen.getAllByTestId('story-step').map((s) => s.textContent)
    expect(steps.some((t) => t?.startsWith('Set designer'))).toBe(true)
    const log = screen.getByTestId('story-log-lines')
    expect(log).toHaveTextContent('Run started')
    await user.click(screen.getByRole('button', { name: 'Errors' }))
    expect(screen.getByTestId('story-log-lines')).not.toHaveTextContent('Run started')
    await user.click(screen.getByRole('button', { name: 'Director' }))
    expect(artifacts).toHaveBeenCalledWith('Show', 'director', 1)
    expect(await screen.findByText('Incoming!')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    await user.click(screen.getByRole('button', { name: 'Cancel run' }))
    expect(cancel).toHaveBeenCalledWith('Show')
  })

  it('settings: a preset sets every model and the tier; keys are shown as set or missing only (F20–F23)', async () => {
    const user = userEvent.setup()
    vi.spyOn(api, 'storySettings').mockResolvedValue(settings)
    const save = vi.spyOn(api, 'storySaveSettings').mockResolvedValue({ ...settings, models: { ...settings.models, llm_model: 'gemini-2.5-flash-lite' }, video: { ...settings.video, active_tier: 'cheapest', active_model: 'veo-3.1-lite' } })
    render(<StorySettingsView />)
    expect(await screen.findByRole('heading', { name: /Quality preset/ })).toHaveTextContent('Balanced')
    expect(screen.getByRole('heading', { name: 'Keys' }).closest('section')).toHaveTextContent('falMissing')
    await user.click(screen.getByRole('button', { name: 'Budget' }))
    expect(screen.getByLabelText('Text (script, story)')).toHaveValue('gemini-2.5-flash-lite')
    expect(screen.getAllByTestId('story-model')).toHaveLength(1)
    await user.click(screen.getByRole('button', { name: 'Save settings' }))
    expect(save).toHaveBeenCalledWith(expect.objectContaining({ llm_model: 'gemini-2.5-flash-lite', active_tier: 'cheapest', active_model: 'veo-3.1-lite', max_budget: 10 }))
    expect(await screen.findByText('Saved. The next run uses these settings.')).toBeInTheDocument()
  })
})

describe('New format, style or project', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    window.localStorage.clear()
  })

  it('offers only catalog options, refuses an existing name and copies a prompt ending with the safety lines', async () => {
    const { NewFormatForm } = await import('./NewFormatView')
    const { realCatalog } = await import('../../test/catalog')
    const { SAFETY_LINES } = await import('../../lib/promptSafety')
    window.localStorage.clear()
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined)
    render(<NewFormatForm catalog={realCatalog()} now={new Date('2026-11-03T10:00:00Z')} />)
    await user.selectOptions(screen.getByLabelText('Project'), 'scalargame')
    await user.selectOptions(screen.getByLabelText('Engine'), 'motion')
    await user.type(screen.getByLabelText('Format name'), 'Progressive Clues')
    await user.type(screen.getByLabelText('Topic'), 'Borders.')
    await user.click(screen.getByRole('button', { name: 'Copy prompt for Claude' }))
    expect(screen.getByText('“progressive-clues” already exists in the catalog; pick another name.')).toBeInTheDocument()
    expect(writeText).not.toHaveBeenCalled()
    await user.clear(screen.getByLabelText('Format name'))
    await user.type(screen.getByLabelText('Format name'), 'Border Run')
    await user.click(screen.getByRole('checkbox', { name: 'map zooms' }))
    await user.click(screen.getByRole('button', { name: 'Copy prompt for Claude' }))
    const prompt = writeText.mock.calls[0]?.[0] ?? ''
    expect(prompt).toMatch(/^New format “Border Run” \(id border-run\) for project scalargame/)
    expect(prompt).toContain('- Visual vocabulary: map zooms')
    expect(prompt.endsWith(SAFETY_LINES.join('\n'))).toBe(true)
    expect(JSON.parse(window.localStorage.getItem('studio-new-format-draft') ?? '{}')).toMatchObject({ name: 'Border Run', project: 'scalargame' })
  })
})
