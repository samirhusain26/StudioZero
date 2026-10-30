import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../../api/client'
import { realCatalog } from '../../test/catalog'
import { MakeBatchView } from '../MakeBatchView'
import { ManualProjectCard } from './ManualProjectCard'
import { StudioView } from './StudioView'
import { PlanMakeContent, suggestedBatchId } from './PlanMakeContent'
import { SAFETY_LINES } from '../../lib/promptSafety'

describe('Studio', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('overview: one card per project in catalog order, with budget, mix and a Make link', async () => {
    vi.spyOn(api, 'catalog').mockResolvedValue(realCatalog())
    vi.spyOn(api, 'schedule').mockRejectedValue(new Error('offline'))
    render(<StudioView />)
    const cards = await screen.findAllByTestId('studio-project')
    expect(cards.map((c) => within(c).getByRole('heading', { level: 2 }).textContent)).toEqual(['Originals · P0', 'Scalargame · P1'])
    expect(cards[0]).toHaveTextContent('every paid run needs your OK with a cost estimate')
    expect(cards[0]).toHaveTextContent('target share not set (your decision)')
    expect(cards[1]).toHaveTextContent('Nothing scheduled')
    expect(within(cards[0] as HTMLElement).getByRole('link', { name: 'Make a Originals batch →' })).toHaveAttribute('href', '#/studio/make?project=originals')
    expect(screen.getByRole('heading', { level: 2, name: 'Engines' })).toBeInTheDocument()
    expect(screen.getAllByTestId('studio-manual-project')).toHaveLength(1)
  })

  it('a hand-posted project: no batch link, the weekly prompt for this or last week, copied as shown', async () => {
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined)
    const project = realCatalog().manualProjects?.find((p) => p.id === 'marathon')
    if (!project) throw new Error('no marathon')
    render(<ManualProjectCard project={project} now={new Date(2026, 9, 18, 9)} />)
    const card = screen.getByTestId('studio-manual-project')
    expect(within(card).getByRole('heading', { level: 2 })).toHaveTextContent('Marathon · posted by hand')
    expect(card).toHaveTextContent(/5 November 2028 · 749 days to go/)
    expect(card).toHaveTextContent('Instagram, TikTok, YouTube Shorts: not named yet')
    expect(within(card).queryByRole('link')).toBeNull()
    await user.click(within(card).getAllByRole('button', { name: 'Copy prompt' })[0] as HTMLElement)
    expect(writeText.mock.calls[0]?.[0]).toMatch(/^\/marathon-week 2026-W42\n\nWeek 2026-W42: Monday 2026-10-12 to Sunday 2026-10-18\./)
    await user.selectOptions(within(card).getByLabelText('Week'), 'last')
    expect(card).toHaveTextContent('/marathon-week 2026-W41')
    expect(card).toHaveTextContent('Read projects/marathon/README.md')
  })

  it('Make a batch: project chips, Originals by its own flow', async () => {
    vi.spyOn(api, 'catalog').mockResolvedValue(realCatalog())
    render(<MakeBatchView project="originals" />)
    const chips = await screen.findByRole('group', { name: 'Project' })
    expect(within(chips).getByRole('link', { name: 'Originals' })).toHaveAttribute('aria-current', 'page')
    expect(within(chips).getByRole('link', { name: 'Scalargame' })).toHaveAttribute('href', '#/studio/make?project=scalargame')
    expect(screen.getByText(/Upload the finalized batch folder in Library › Add batch/)).toBeInTheDocument()
  })

  it('Originals: subjects make the prompt; checks are kept per batch id in this browser', async () => {
    window.localStorage.clear()
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined)
    const catalog = realCatalog()
    const project = catalog.projects.find((p) => p.id === 'originals')
    if (!project) throw new Error('no originals')
    render(<PlanMakeContent catalog={catalog} project={project} now={new Date('2026-11-03T10:00:00Z')} />)
    expect(screen.getByLabelText('Batch id')).toHaveValue('2026-11-o01')
    expect(screen.getByRole('button', { name: 'Copy prompt for Claude' })).toBeDisabled()
    await user.type(screen.getByLabelText('Subjects (one title or story idea per line)'), 'Arrival (2016)')
    await user.click(screen.getByRole('button', { name: 'Copy prompt for Claude' }))
    const prompt = writeText.mock.calls[0]?.[0] ?? ''
    expect(prompt).toMatch(/^\/originals brief 2026-11-o01\n/)
    expect(prompt).toContain('- Arrival (2016)')
    expect(prompt.endsWith(SAFETY_LINES.join('\n'))).toBe(true)
    const list = screen.getByTestId('make-checklist')
    expect(within(list).getAllByRole('checkbox').map((b) => b.closest('div')?.textContent)).toEqual([
      'Checkpoint 0: brief, titles and cost estimates approved',
      'Each paid run approved with its estimate (actual cost reported after)',
      'Checkpoint 1: scripts (fact-check), rights, frames and AI disclosure',
      'Checkpoint 2: captions, platforms and AI labels; each video watched with sound',
      'Finalize (only on your approval)',
    ])
    await user.click(within(list).getByRole('checkbox', { name: /^Checkpoint 0/ }))
    expect(JSON.parse(window.localStorage.getItem('studio-make-originals') ?? '{}')).toEqual({ batchId: '2026-11-o01', checks: ['checkpoint-0'] })
    expect(suggestedBatchId('originals', new Date('2027-01-31T23:00:00Z'))).toBe('2027-01-o01')
    expect(suggestedBatchId('newproject', new Date('2027-01-31T23:00:00Z'))).toBe('2027-01-newproject-01')
    window.localStorage.clear()
  })
})
