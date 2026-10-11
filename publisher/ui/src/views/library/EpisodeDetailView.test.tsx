import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { EpisodeDetail, LibraryEpisode } from '../../api/types'
import { PLATFORMS } from '../../api/types'
import { EpisodeDetailContent } from './EpisodeDetailView'

const { api } = vi.hoisted(() => ({ api: { saveFeedback: vi.fn(), clearFeedback: vi.fn(), approveContent: vi.fn() } }))
vi.mock('../../api/client', async (importOriginal) => ({ ...(await importOriginal<typeof import('../../api/client')>()), api }))

function detail(): EpisodeDetail {
  return {
    batchId: '2026-10-b01',
    episode: {
      episodeId: 'scalar-clues-001',
      questionId: 'scalar:BOL:clues',
      revision: 1,
      game: 'scalar',
      format: 'progressive-clues',
      language: 'en',
      difficulty: 'moderate',
      styleId: 'scalar-v1',
      experimentId: null,
      variantId: null,
      creative: {
        hook: 'Three clues. One country.',
        question: 'Which country is it?',
        clues: ['Landlocked', 'Two capitals', 'Lake Titicaca'],
        choices: [
          { key: 'A', label: 'Paraguay' },
          { key: 'B', label: 'Bolivia' },
          { key: 'C', label: 'Austria' },
        ],
        answer: 'Bolivia',
        answerAliases: ['Plurinational State of Bolivia'],
        explanation: 'Sucre and La Paz share the role.',
      },
      evidence: {
        sources: [{ title: 'Bolivia — CIA World Factbook', url: 'https://www.cia.gov/the-world-factbook/countries/bolivia/', retrieved: '2026-10-01' }],
        checks: { uniqueAnswer: true, candidateCounts: [12, 4, 1] },
        reviewer: 'owner',
      },
      music: { trackId: 'bed-03', sha256: 'd'.repeat(64), license: 'Owner-made, all rights' },
      video: { file: 'videos/scalar-clues-001.mp4', sha256: 'a'.repeat(64), bytes: 4_000_000, durationSeconds: 21.5, width: 1080, height: 1920, fps: '30/1', videoCodec: 'h264', audioCodec: 'aac' },
      cover: { file: 'covers/scalar-clues-001.jpg', sha256: 'b'.repeat(64), bytes: 120_000 },
      publication: {
        deepLink: '/scalar',
        utmCampaign: 'social_v1',
        captions: { instagram: 'Three clues, one country. Can you get it?', x: 'Three clues. Which country? {link}' },
        youtube: null,
        altText: 'Map silhouette with three clues',
        hashtags: ['#geography'],
        credits: [],
        poll: { question: 'Which one?', options: ['Paraguay', 'Bolivia', 'Austria'] },
        firstComment: { instagram: 'Answer tomorrow!' },
        answerReply: { text: '\n\nIt was Bolivia!', delayHours: 24 },
      },
      eligibility: { status: 'qa-passed', notBefore: null, reviewBy: '2027-01-01', expiresAt: null },
    },
    approval: null,
    notes: {
      batchId: '2026-10-b01',
      brief: { batchId: '2026-10-b01', kind: 'brief', text: '# Brief\nInclude Bolivia as a hard one.', sha256: 'e'.repeat(64), bytes: 40, uploadedAt: '2026-10-01T10:00:00Z' },
      retro: null,
    },
    feedback: null,
    posts: [{ platform: 'instagram', status: 'confirmed', at: '2026-10-12T13:00:05Z', permalink: 'https://www.instagram.com/p/abc/', metrics: { checkpoint: '24h', fetchedAt: '2026-10-13T13:20:00Z', status: 'ok', values: { views: 1500 } } }],
  }
}

const SPOILERS = [/Plurinational/, /Sucre and La Paz/, /It was Bolivia/, /CIA World Factbook/, /Include Bolivia/, /scalar:BOL:clues/]

describe('EpisodeDetailContent posts', () => {
  it('shows the newest stats read under each post', () => {
    render(<EpisodeDetailContent episodeId="scalar-clues-001" revision={1} detail={detail()} zone="UTC" />)
    expect(screen.getByText('1.5k views (at 24h)')).toBeInTheDocument()
  })
})

describe('EpisodeDetailContent spoiler safety', () => {
  it('hides the answer, correct choice, explanation, aliases, sources, answer reply and notes by default', async () => {
    render(<EpisodeDetailContent episodeId="scalar-clues-001" revision={1} detail={detail()} zone="UTC" />)
    const question = screen.getByTestId('episode-question')
    // The puzzle itself is visible.
    expect(within(question).getByText('Which country is it?')).toBeInTheDocument()
    expect(within(question).getByText('Lake Titicaca')).toBeInTheDocument()
    expect(question).toHaveTextContent('B Bolivia') // as a choice label, unmarked
    expect(screen.queryByText('Correct')).toBeNull()
    expect(within(screen.getByTestId('answer-area')).queryByText(/Bolivia/)).toBeNull()
    for (const spoiler of SPOILERS) expect(document.body.textContent ?? '').not.toMatch(spoiler)

    const toggle = screen.getByRole('button', { name: 'Reveal answer' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await userEvent.setup().click(toggle)
    expect(screen.getByRole('button', { name: 'Hide answer' })).toHaveAttribute('aria-expanded', 'true')
    for (const spoiler of SPOILERS.filter((s) => s.source !== 'Include Bolivia')) expect(document.body.textContent ?? '').toMatch(spoiler)
    const correct = screen.getByText('Correct').closest('li')
    expect(correct).toHaveTextContent('B Bolivia')
    expect(screen.getByRole('link', { name: 'Bolivia — CIA World Factbook' })).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('resets to hidden on navigation (a new episode route remounts the view)', async () => {
    const { rerender } = render(<EpisodeDetailContent key="a" episodeId="scalar-clues-001" revision={1} detail={detail()} zone="UTC" />)
    await userEvent.setup().click(screen.getByRole('button', { name: 'Reveal answer' }))
    expect(document.body.textContent).toMatch(/Sucre and La Paz/)
    rerender(<EpisodeDetailContent key="b" episodeId="scalar-clues-001" revision={2} detail={detail()} zone="UTC" />)
    expect(screen.getByRole('button', { name: 'Reveal answer' })).toBeInTheDocument()
    expect(document.body.textContent).not.toMatch(/Sucre and La Paz/)
  })
})

describe('FeedbackEditor', () => {
  beforeEach(() => {
    api.saveFeedback.mockReset().mockImplementation((episodeId: string, revision: number, body: { tags: string[]; note: string }) =>
      Promise.resolve({ episodeId, revision, ...body, status: 'open', updatedAt: '2026-10-20T12:00:00Z' }),
    )
  })

  it('toggles tag chips, counts the note and saves in contract tag order', async () => {
    const user = userEvent.setup()
    render(<EpisodeDetailContent episodeId="scalar-clues-001" revision={1} detail={detail()} zone="UTC" />)
    // On a phone, Feedback opens the editor in a bottom sheet.
    expect(screen.queryByTestId('feedback-editor')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Feedback' }))
    const sheet = screen.getByRole('dialog', { name: 'Feedback' })
    const editor = within(sheet).getByTestId('feedback-editor')
    const save = within(editor).getByRole('button', { name: 'Save feedback' })
    expect(save).toBeDisabled()
    await user.click(within(editor).getByRole('button', { name: 'Music' }))
    await user.click(within(editor).getByRole('button', { name: 'Weak hook' }))
    expect(within(editor).getByRole('button', { name: 'Weak hook' })).toHaveAttribute('aria-pressed', 'true')
    await user.type(within(editor).getByLabelText('Note'), 'Hook too slow')
    expect(within(editor).getByText(/13 \/ 2000/)).toBeInTheDocument()
    expect(within(editor).getByText(/Unsaved changes/)).toBeInTheDocument()
    await user.click(save)
    await waitFor(() => expect(api.saveFeedback).toHaveBeenCalledWith('scalar-clues-001', 1, { tags: ['hook-weak', 'music'], note: 'Hook too slow' }))
    expect(await within(editor).findByText(/Feedback saved/)).toBeInTheDocument()
    expect(within(editor).getByRole('button', { name: 'Clear' })).toBeEnabled()
  })
})

function entry(over: Partial<LibraryEpisode> = {}): LibraryEpisode {
  const d = detail()
  return {
    episodeId: 'scalar-clues-001', revision: 1, batchId: '2026-10-b01', questionId: 'scalar:BOL:clues', game: 'scalar', format: 'progressive-clues',
    difficulty: 'moderate', status: 'reviewable', statusLabel: 'Ready for review', metadataSha256: 'c'.repeat(64), videoSha256: 'a'.repeat(64),
    coverSha256: 'b'.repeat(64), videoUrl: '/api/media/videos/x.mp4?t=1', coverUrl: null, media: null, videoRemovedAt: null,
    platforms: Object.fromEntries(PLATFORMS.map((p) => [p, { eligible: true, reason: null }])) as LibraryEpisode['platforms'], problems: [], approvals: [], currentApproval: null, inManifest: false, deletable: true,
    legacy: false, variants: [], postedOn: [], episode: d.episode as unknown as LibraryEpisode['episode'], ...over,
  }
}

describe('Review actions', () => {
  beforeEach(() => {
    api.approveContent.mockReset().mockResolvedValue({ results: [{ episodeId: 'scalar-clues-001', revision: 1, ok: true, status: 'approved', message: null }] })
  })

  it('has one sticky bar: Approve (primary), Feedback, Next → the next episode in the list', () => {
    const next = entry({ episodeId: 'scalar-clues-002' })
    render(
      <EpisodeDetailContent episodeId="scalar-clues-001" revision={1} detail={detail()} entry={entry()} zone="UTC"
        neighbours={{ index: 0, total: 2, previous: null, next }} />,
    )
    const bar = screen.getByRole('group', { name: 'Review actions' })
    expect(within(bar).getAllByRole('button').map((b) => b.textContent)).toEqual(['Approve', 'Feedback'])
    expect(within(bar).getByRole('button', { name: 'Approve' })).toHaveClass('btn-primary')
    expect(within(bar).getByRole('link', { name: 'Next →' })).toHaveAttribute('href', '#/library/episode/scalar-clues-002/1')
    expect(document.querySelectorAll('.btn-primary')).toHaveLength(1)
  })

  it('approves with the existing confirmation, recording the reviewer', async () => {
    const user = userEvent.setup()
    const onChanged = vi.fn()
    render(<EpisodeDetailContent episodeId="scalar-clues-001" revision={1} detail={detail()} entry={entry()} zone="UTC" onChanged={onChanged} />)
    await user.click(screen.getByRole('button', { name: 'Approve' }))
    const dialog = screen.getByRole('dialog', { name: 'Approve 1 video?' })
    await user.clear(within(dialog).getByLabelText('Reviewer name'))
    expect(within(dialog).getByRole('button', { name: 'Approve' })).toBeDisabled()
    await user.type(within(dialog).getByLabelText('Reviewer name'), 'Samir')
    await user.click(within(dialog).getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(api.approveContent).toHaveBeenCalledWith({ items: [{ episodeId: 'scalar-clues-001', revision: 1 }], reviewer: 'Samir' }))
    expect(onChanged).toHaveBeenCalled()
    expect(await screen.findByText('Approved 1 of 1.')).toBeInTheDocument()
  })

  it('cannot approve an approved or invalid episode; at the end Next becomes Done', () => {
    const { rerender } = render(<EpisodeDetailContent episodeId="scalar-clues-001" revision={1} detail={detail()} entry={entry({ status: 'approved' })} zone="UTC" />)
    expect(screen.getByRole('button', { name: 'Approved ✓' })).toBeDisabled()
    expect(screen.getByRole('link', { name: 'Done: back to the Library' })).toHaveAttribute('href', '#/library')
    rerender(<EpisodeDetailContent episodeId="scalar-clues-001" revision={1} detail={detail()} entry={entry({ problems: [{ code: 'media', path: 'video', message: 'Bad' }] })} zone="UTC" />)
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled()
  })
})
