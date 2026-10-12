import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api/client'
import type { FeedbackItem, MetricsStatus, NextBatchInfo } from '../api/types'
import { FEEDBACK_TAGS } from '../api/types'
import { SAFETY_LINES } from '../lib/promptSafety'
import { realCatalog } from '../test/catalog'
import { MakeBatchContent } from './MakeBatchView'

const catalog = realCatalog()

const empty: NextBatchInfo = { nextBatchId: '2026-11-b02', openFeedback: [], lastBrief: null, lastRetro: null, performance: [], accounts: [], funnel: [], tags: [...FEEDBACK_TAGS] }

const item = (over: Partial<FeedbackItem>): FeedbackItem => ({
  episodeId: 'scalar-clues-001',
  revision: 1,
  tags: [],
  note: '',
  status: 'open',
  updatedAt: '2026-10-15T10:00:00Z',
  batchId: '2026-10-b01',
  questionId: 'scalar:BOL:clues',
  game: 'scalar',
  format: 'progressive-clues',
  styleId: 'scalar-v1',
  ...over,
})

const statsOff: MetricsStatus = { enabled: false, pending: null, lastRun: null, timer: null, pathActive: true }

describe('Make a batch', () => {
  beforeEach(() => {
    vi.spyOn(api, 'getMetricsStatus').mockResolvedValue(statsOff)
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('opens How the posts did with the post stats controls, then the per-video funnel', async () => {
    const info: NextBatchInfo = {
      ...empty,
      funnel: [
        {
          episode: 'scalar-clues-001',
          publishedDates: ['2026-10-05'],
          views: 1500,
          engaged: null,
          answered: null,
          avgWatchSeconds: null,
          followsThatDay: 4,
          counted: { views: ['instagram'], engaged: [], answered: [], avgWatchSeconds: [], followsThatDay: ['instagram'] },
          platforms: {},
        },
      ],
    }
    render(<MakeBatchContent catalog={catalog} info={info} fromCommit={null} onChanged={vi.fn()} />)
    const how = screen.getByText('How the posts did').closest('details') as HTMLElement
    const sections = [...how.querySelectorAll('h3')].map((h) => h.textContent)
    expect(sections).toEqual(['Post stats', 'Per video', 'Accounts, last 7 days', 'Performance'])
    expect(await within(how).findByRole('button', { name: 'Hourly reads', pressed: false })).toHaveAttribute('aria-pressed', 'false')
    expect(within(how).getByRole('rowheader', { name: /scalar-clues-001/ })).toBeInTheDocument()
    expect(document.querySelectorAll('.btn-primary')).toHaveLength(1)
    expect(screen.getByRole('button', { name: 'Copy prompt for Claude' })).toHaveClass('btn-primary')
  })

  it('explains the next action when there is nothing yet', () => {
    render(<MakeBatchContent catalog={catalog} info={empty} fromCommit={null} onChanged={vi.fn()} />)
    expect(screen.getByText(/No open feedback yet/)).toBeInTheDocument()
    expect(screen.getByText(/No retro uploaded yet\. After a batch has posted/)).toBeInTheDocument()
    expect(screen.getByText('No brief uploaded yet. Add BRIEF.md to a batch in step 5.')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Show last brief/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Show notes/ })).not.toBeInTheDocument()
    expect(screen.getByText(/No posts with links yet/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Mark these notes as used/ })).toBeDisabled()
  })

  it('shows account stats for the last 7 days, with a note when a platform cannot be read', () => {
    const accounts: NextBatchInfo['accounts'] = [
      { platform: 'instagram', followers: 1200, followersChange: 35, days: 7, totals: { impressions: 6300, engagements: 315, engagement_rate: 0.05 }, status: 'ok' },
      { platform: 'facebook', followers: null, followersChange: null, days: 0, totals: {}, status: 'authorization' },
    ]
    render(<MakeBatchContent catalog={catalog} info={{ ...empty, accounts }} fromCommit={null} onChanged={vi.fn()} />)
    const row = screen.getByRole('rowheader', { name: 'Instagram' }).closest('tr')
    expect(row).toHaveTextContent('1.2k (+35)6.3k3155.0%—')
    expect(screen.getByText('Stats need the insights permission for this account')).toBeInTheDocument()
  })

  it('copies exactly the hand-off prompt with the edited brief, kept across hide and show', async () => {
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined)
    render(<MakeBatchContent catalog={catalog} info={empty} fromCommit={null} onChanged={vi.fn()} />)
    expect(screen.queryByLabelText('Brief (Markdown)')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Show brief (may contain answers)' }))
    const brief = screen.getByLabelText('Brief (Markdown)')
    expect((brief as HTMLTextAreaElement).value).toContain('# Brief: 2026-11-b02')
    await user.clear(brief)
    await user.type(brief, 'Make 12 episodes.')
    await user.click(screen.getByRole('button', { name: 'Hide brief' }))
    expect(screen.queryByLabelText('Brief (Markdown)')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Show brief (may contain answers)' }))
    expect((screen.getByLabelText('Brief (Markdown)') as HTMLTextAreaElement).value).toBe('Make 12 episodes.')
    await user.click(screen.getByRole('button', { name: 'Copy prompt for Claude' }))
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(`/video-batch brief 2026-11-b02\n\nMake 12 episodes.\n\nFeedback file: library/_inbox/feedback-2026-11-b02.json\n\n${SAFETY_LINES.join('\n')}`),
    )
    expect(screen.getByText(/Prompt copied/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Reset to template' }))
    expect((screen.getByLabelText('Brief (Markdown)') as HTMLTextAreaElement).value).toContain('## What to fix')
  })

  it('builds the brief from catalog choices and blocks the copy while a choice is invalid', async () => {
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined)
    render(<MakeBatchContent catalog={catalog} info={empty} fromCommit={null} onChanged={vi.fn()} />)
    const builder = screen.getByTestId('prompt-builder')
    expect(within(builder).getAllByRole('row')).toHaveLength(9)
    const clues = within(builder).getByLabelText('Progressive clues (scalar): episodes')
    await user.clear(clues)
    await user.type(clues, '5')
    expect(within(builder).getByLabelText('Progressive clues (scalar): approachable')).toHaveValue(2)
    await user.clear(within(builder).getByLabelText('Progressive clues (scalar): challenging'))
    expect(screen.getByTestId('plan-problems')).toHaveTextContent('Progressive clues: the difficulty mix must add up to 5.')
    expect(screen.getByRole('button', { name: 'Copy prompt for Claude' })).toBeDisabled()
    await user.type(within(builder).getByLabelText('Progressive clues (scalar): challenging'), '1')
    expect(screen.queryByTestId('plan-problems')).not.toBeInTheDocument()
    const music = within(builder).getByLabelText('Head to head (continuum): music') as HTMLSelectElement
    expect([...music.options].map((o) => o.value)).toContain('continuum-20-holizna-clouds')
    expect([...music.options].some((o) => o.value === 'continuum-20')).toBe(false)
    await user.selectOptions(music, 'continuum-20-holizna-clouds')
    await user.click(screen.getByRole('button', { name: 'Copy prompt for Claude' }))
    await waitFor(() => expect(writeText).toHaveBeenCalled())
    const prompt = writeText.mock.calls[0]?.[0] ?? ''
    expect(prompt).toContain('- scalar / progressive-clues: 5 (approachable 2, moderate 2, challenging 1)')
    expect(prompt).toContain('head-to-head → continuum-20-holizna-clouds')
    expect(prompt.endsWith(SAFETY_LINES.join('\n'))).toBe(true)
  })

  it('saves and applies presets in this browser only', async () => {
    const user = userEvent.setup()
    window.localStorage.clear()
    render(<MakeBatchContent catalog={catalog} info={empty} fromCommit={null} onChanged={vi.fn()} />)
    const builder = screen.getByTestId('prompt-builder')
    await user.type(within(builder).getByLabelText('Goal'), 'Shorter hooks')
    await user.type(within(builder).getByLabelText('Save these choices as'), 'Hooks')
    await user.click(within(builder).getByRole('button', { name: 'Save preset' }))
    expect(within(builder).getByText(/Saved “Hooks” in this browser/)).toBeInTheDocument()
    await user.clear(within(builder).getByLabelText('Goal'))
    await user.selectOptions(within(builder).getByLabelText('Preset'), 'Hooks')
    await user.click(within(builder).getByRole('button', { name: 'Apply' }))
    expect(within(builder).getByLabelText('Goal')).toHaveValue('Shorter hooks')
    expect(window.localStorage.getItem('studio-prompt-presets')).not.toContain('2026-11-b02')
    window.localStorage.clear()
  })

  it('copies the template prompt while the brief is hidden', async () => {
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined)
    render(<MakeBatchContent catalog={catalog} info={empty} fromCommit={null} onChanged={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: 'Copy prompt for Claude' }))
    await waitFor(() => expect(writeText).toHaveBeenCalled())
    const prompt = writeText.mock.calls[0]?.[0] ?? ''
    expect(prompt).toMatch(/^\/video-batch brief 2026-11-b02\n\n# Brief: 2026-11-b02/)
    expect(prompt).toContain('Feedback file: library/_inbox/feedback-2026-11-b02.json')
    expect(screen.queryByLabelText('Brief (Markdown)')).not.toBeInTheDocument()
  })

  it('hides feedback notes until revealed, keeping tags visible', async () => {
    const user = userEvent.setup()
    const info: NextBatchInfo = {
      ...empty,
      openFeedback: [
        item({ tags: ['great-reveal'], note: 'The answer was Bolivia.' }),
        item({ episodeId: 'tectonic-neighbors-003', tags: ['hook-weak'], note: '' }),
      ],
    }
    render(<MakeBatchContent catalog={catalog} info={info} fromCommit={null} onChanged={vi.fn()} />)
    expect(screen.queryByText('The answer was Bolivia.')).not.toBeInTheDocument()
    expect(screen.getAllByText('Note hidden')).toHaveLength(1)
    expect(screen.getByText('Great reveal')).toBeInTheDocument()
    expect(screen.getByText('Weak hook')).toBeInTheDocument()
    const toggle = screen.getByRole('button', { name: 'Show notes (may contain answers)' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(document.getElementById(toggle.getAttribute('aria-controls') ?? '')).not.toBeNull()
    await user.click(toggle)
    expect(screen.getByText('The answer was Bolivia.')).toBeInTheDocument()
    expect(screen.queryByText('Note hidden')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Hide notes' }))
    expect(screen.queryByText('The answer was Bolivia.')).not.toBeInTheDocument()
  })

  it('shows the last brief only behind its toggle', async () => {
    const user = userEvent.setup()
    const info: NextBatchInfo = {
      ...empty,
      lastBrief: { batchId: '2026-10-b01', kind: 'brief', text: '# Brief\nInclude Bolivia.', sha256: 'b'.repeat(64), bytes: 24, uploadedAt: '2026-10-10T09:00:00Z' },
    }
    render(<MakeBatchContent catalog={catalog} info={info} fromCommit={null} onChanged={vi.fn()} />)
    expect(screen.getByText(/Brief: batch 2026-10-b01 · uploaded/)).toBeInTheDocument()
    expect(screen.queryByText('Include Bolivia.')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Show last brief (may contain answers)' }))
    expect(screen.getByText('Include Bolivia.')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Hide last brief' }))
    expect(screen.queryByText('Include Bolivia.')).not.toBeInTheDocument()
  })

  it('is the Mac step shown in the UI: numbered steps, labelled on the Mac, with a local checklist', async () => {
    window.localStorage.clear()
    const user = userEvent.setup()
    render(<MakeBatchContent catalog={catalog} info={empty} fromCommit={null} onChanged={vi.fn()} lastBatchId="2026-10-b01" />)
    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)
    expect(headings).toEqual([
      '1Carry feedback overhere on the Pi',
      '2Write the briefhere on the Pi',
      '3Let Claude make iton the Mac',
      '4Upload ithere on the Pi',
      '5Retro, after postingon the Mac',
    ])
    expect(screen.getByText('cd ~/Personal/code_projects/scalargame/marketing && claude')).toBeInTheDocument()
    expect(screen.getByText('/video-batch retro 2026-10-b01')).toBeInTheDocument()
    expect(document.querySelectorAll('.btn-primary')).toHaveLength(1)
    const list = screen.getByTestId('make-checklist')
    const boxes = within(list).getAllByRole('checkbox')
    expect(boxes).toHaveLength(5)
    await user.click(within(list).getByRole('checkbox', { name: /Checkpoint 1/ }))
    await user.click(within(list).getByRole('checkbox', { name: /Finalize/ }))
    expect(JSON.parse(window.localStorage.getItem('scalar-make-2026-11-b02') ?? '{}')).toEqual({ started: true, checks: ['c1', 'finalize'] })
    await user.click(within(list).getByRole('checkbox', { name: /Checkpoint 1/ }))
    expect(JSON.parse(window.localStorage.getItem('scalar-make-2026-11-b02') ?? '{}')).toEqual({ started: true, checks: ['finalize'] })
  })

  it('downloading feedback.json marks the batch as started in this browser', async () => {
    window.localStorage.clear()
    const user = userEvent.setup()
    URL.createObjectURL = vi.fn(() => 'blob:x')
    URL.revokeObjectURL = vi.fn()
    render(<MakeBatchContent catalog={catalog} info={empty} fromCommit={null} onChanged={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: 'Download feedback-2026-11-b02.json' }))
    expect(JSON.parse(window.localStorage.getItem('scalar-make-2026-11-b02') ?? '{}')).toEqual({ started: true, checks: [] })
  })
})

