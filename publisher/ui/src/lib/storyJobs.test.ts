import { describe, expect, it } from 'vitest'
import type { StoryEvent, StoryProject, StoryProjectDetail, StorySettings } from '../api/types'
import {
  budgetView,
  createProblems,
  detectPreset,
  EPISODE_STEPS,
  eventText,
  filterEvents,
  lastUpdateText,
  mergeEvents,
  parseScript,
  pollingNote,
  projectInfo,
  runAction,
  stepRail,
  tierBadge,
  usd,
  wordCount,
} from './storyJobs'

const ev = (seq: number, kind: string, message = '', data?: StoryEvent['data']): StoryEvent => ({
  seq,
  at: `2026-10-12T10:00:${String(seq).padStart(2, '0')}Z`,
  kind,
  message,
  ...(data ? { data } : {}),
})

const project = (over: Partial<StoryProject> = {}): StoryProject => ({
  id: 'Show',
  name: 'Show',
  route: 'series',
  params: { num_episodes: 2 },
  status: 'paused',
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

const done = (from: string, to: string, artifacts = 1) => ({ completed: true, startedAt: from, completedAt: to, error: null, artifacts })

const settings: StorySettings = {
  models: { llm_model: 'gemini-2.5-flash', image_model: 'gemini-2.5-flash-image', tts_model: 'gemini-2.5-flash-preview-tts' },
  choices: { llm_model: [], image_model: [], tts_model: [] },
  video: { active_model: 'veo-3.1-fast', active_tier: 'recommended', max_budget: 10, auto_downgrade: true },
  tiers: {
    recommended: [
      { id: 'veo-3.1-fast', name: 'Veo 3.1 Fast', provider: 'gemini', costPerSecondUsd: 0.15, maxResolution: '1080p', maxDurationSeconds: 8, audio: true, referenceImages: true, description: '', episodeUsd: 7.2 },
    ],
    cheapest: [
      { id: 'veo-3.1-lite', name: 'Veo 3.1 Lite', provider: 'gemini', costPerSecondUsd: 0.05, maxResolution: '720p', maxDurationSeconds: 8, audio: true, referenceImages: false, description: '', episodeUsd: 2.4 },
    ],
  },
  presets: {
    budget: { llm_model: 'gemini-2.5-flash-lite', image_model: 'gemini-2.5-flash-image', tts_model: 'gemini-2.5-flash-preview-tts', tier: 'cheapest' },
    balanced: { llm_model: 'gemini-2.5-flash', image_model: 'gemini-2.5-flash-image', tts_model: 'gemini-2.5-flash-preview-tts', tier: 'recommended' },
  },
  keys: {},
}

describe('stepRail', () => {
  it('includes set_designer in every episode and marks phases (B7)', () => {
    expect(EPISODE_STEPS).toContain('set_designer')
    const rail = stepRail(
      {
        seriesSteps: { writer: done('2026-10-12T10:00:00Z', '2026-10-12T10:00:25Z'), screenwriter: { completed: false, startedAt: null, completedAt: null, error: 'quota', artifacts: 0 } },
        episodes: { '1': { director: done('2026-10-12T10:01:00Z', '2026-10-12T10:01:30Z'), set_designer: { completed: false, startedAt: '2026-10-12T10:02:00Z', completedAt: null, error: null, artifacts: 0 } } },
      },
      2,
      true,
    )
    expect(rail.preProduction.map((s) => s.phase)).toEqual(['done', 'error', 'pending', 'pending'])
    expect(rail.preProduction[0]?.seconds).toBe(25)
    expect(rail.episodes).toHaveLength(2)
    expect(rail.episodes[0]?.steps.map((s) => s.phase)).toEqual(['done', 'running', 'pending', 'pending'])
    expect(rail.episodes[0]?.phase).toBe('running')
    expect(rail.episodes[1]?.phase).toBe('pending')
  })

  it('shows an interrupted step as pending when nothing runs, and a missing state as all pending', () => {
    const rail = stepRail({ seriesSteps: { writer: { completed: false, startedAt: '2026-10-12T10:00:00Z', completedAt: null, error: null, artifacts: 0 } }, episodes: {} }, 1, false)
    expect(rail.preProduction[0]?.phase).toBe('pending')
    expect(stepRail(null, 1, false).episodes[0]?.steps.every((s) => s.phase === 'pending')).toBe(true)
  })
})

describe('projectInfo', () => {
  it('counts steps, time and clips', () => {
    const detail: StoryProjectDetail = {
      ...project({ params: { num_episodes: 1 } }),
      pipelineState: {
        seriesSteps: { writer: done('2026-10-12T10:00:00Z', '2026-10-12T10:00:10Z', 2) },
        episodes: { '1': { scene_generator: done('2026-10-12T10:01:00Z', '2026-10-12T10:02:00Z', 5) } },
      },
    }
    expect(projectInfo(detail)).toEqual({ stepsDone: 2, stepsTotal: 8, totalSeconds: 70, clips: 5, files: 7 })
  })
})

describe('budget and money', () => {
  it('caps the bar and flags over-budget', () => {
    expect(budgetView(2.5, 10)).toEqual({ spentUsd: 2.5, maxUsd: 10, remainingUsd: 7.5, percent: 25, over: false })
    expect(budgetView(12, 10)).toMatchObject({ percent: 100, over: true, remainingUsd: 0 })
    expect(budgetView(0, 0).percent).toBe(0)
    expect(usd(1.5)).toBe('$1.50')
    expect(usd(0.025)).toBe('$0.025')
  })
})

describe('events', () => {
  const events = [ev(1, 'status', 'Run started'), ev(2, 'step', '[ep1/director] Starting'), ev(3, 'error', 'quota'), ev(4, 'veo_polling', '', { scene_id: 3, elapsed: 80, model: 'veo-3.1-fast' })]

  it('filters, merges without duplicates and caps', () => {
    expect(filterEvents(events, 'errors').map((e) => e.seq)).toEqual([3])
    expect(filterEvents(events, 'steps').map((e) => e.seq)).toEqual([2, 3, 4])
    expect(mergeEvents(events.slice(0, 2), events.slice(1)).map((e) => e.seq)).toEqual([1, 2, 3, 4])
    expect(mergeEvents(events, [ev(5, 'step')], 3).map((e) => e.seq)).toEqual([3, 4, 5])
  })

  it('describes polling and cost updates, and the polling note only while running (F16)', () => {
    expect(eventText(events[3] as StoryEvent)).toBe('Scene 3: waiting for veo-3.1-fast · 1m 20s')
    expect(eventText(ev(6, 'cost_update', '', { scene_id: 3, scene_cost: 1.2, model_name: 'Veo 3.1 Fast' }))).toBe('Scene 3 rendered with Veo 3.1 Fast · $1.20')
    expect(pollingNote(events, true)).toContain('Scene 3')
    expect(pollingNote(events, false)).toBeNull()
    expect(pollingNote(events.slice(0, 3), true)).toBeNull()
    expect(lastUpdateText(events, Date.parse('2026-10-12T10:00:16Z'))).toBe('Last update 12s ago')
    expect(lastUpdateText([], 0)).toBeNull()
  })
})

describe('runAction', () => {
  it('runs only when no decision is pending (F7, F14, F15, F18)', () => {
    expect(runAction(project({ status: 'created' }))).toEqual({ kind: 'run', label: 'Start' })
    expect(runAction(project({ status: 'error' }))).toEqual({ kind: 'run', label: 'Retry' })
    expect(runAction(project({ status: 'review' })).kind).toBe('none')
    expect(runAction(project({ status: 'scene_failed' })).kind).toBe('none')
    expect(runAction(project({ status: 'paused', running: true })).kind).toBe('none')
    expect(runAction(project({ status: 'completed' })).kind).toBe('none')
  })
})

describe('settings', () => {
  it('detects presets and labels the tier (F13, F20)', () => {
    expect(detectPreset(settings)).toBe('balanced')
    expect(detectPreset({ ...settings, models: { ...settings.models, llm_model: 'gemini-2.5-pro' } })).toBe('custom')
    expect(tierBadge(settings)).toBe('Recommended · Veo 3.1 Fast')
    expect(tierBadge(settings, 'veo-3.1-lite')).toBe('Budget · Veo 3.1 Lite')
  })
})

describe('forms', () => {
  it('checks create forms, scripts and word counts', () => {
    expect(createProblems({ route: 'recap', name: ' ', brief: '', episodes: 1 })).toEqual(['Type a movie name or a story idea.'])
    expect(createProblems({ route: 'series', name: 'A', brief: '', episodes: 11 })).toEqual(['A series needs a brief.', 'Episodes: 1 to 10.'])
    expect(createProblems({ route: 'series', name: 'A', brief: 'b', episodes: 3 })).toEqual([])
    expect(parseScript('{"title": "x"}')).toEqual({ script: { title: 'x' } })
    expect(parseScript('[1]')).toEqual({ error: 'The script must be a JSON object.' })
    expect('error' in parseScript('{')).toBe(true)
    expect(wordCount('  a b\nc ')).toBe(3)
    expect(wordCount('')).toBe(0)
  })
})
