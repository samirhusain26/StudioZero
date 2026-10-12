import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { libraryFixture } from '../../test/libraryFixture'
import { LibraryBrowser } from './LibraryView'

beforeEach(() => sessionStorage.clear())

describe('Library list', () => {
  it('shows To review by default, with batch chips and one tap-to-review card per episode', () => {
    render(<LibraryBrowser data={libraryFixture()} onChanged={vi.fn()} />)
    const show = screen.getByRole('group', { name: 'Show' })
    expect(within(show).getByRole('button', { name: /^To review/ })).toHaveAttribute('aria-pressed', 'true')
    expect(within(show).getByRole('button', { name: /^To review/ })).toHaveTextContent('To review ● 3')
    const batches = within(screen.getByRole('group', { name: 'Batch' })).getAllByRole('button').map((b) => b.textContent)
    expect(batches).toEqual(['All batches · 4', '2026-10-b01 · 3', 'legacy · 1'])
    const cards = screen.getAllByTestId('episode-card')
    expect(cards).toHaveLength(3)
    expect(cards[0]).toHaveAttribute('href', '#/library/episode/scalar-clues-001/1')
    expect(cards[0]).toHaveTextContent('Question 1?')
    expect(within(cards[0] as HTMLElement).queryByRole('button')).toBeNull()
    expect(screen.queryByRole('combobox')).toBeNull()
  })

  it('Approve all shown sits in the sticky bar only for To review with two or more shown', async () => {
    const user = userEvent.setup()
    render(<LibraryBrowser data={libraryFixture()} onChanged={vi.fn()} />)
    const bar = screen.getByRole('group', { name: 'Library actions' })
    await user.click(within(bar).getByRole('button', { name: 'Approve all shown (3)' }))
    expect(screen.getByRole('dialog', { name: 'Approve 3 videos?' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await user.click(within(screen.getByRole('group', { name: 'Show' })).getByRole('button', { name: 'Approved' }))
    expect(screen.queryByRole('group', { name: 'Library actions' })).toBeNull()
    expect(screen.getAllByTestId('episode-card')).toHaveLength(1)
    expect(JSON.parse(sessionStorage.getItem('scalar-library-list') ?? '{}')).toEqual({ batchId: '', filter: 'approved' })
  })

  it('empty states point back to Make a batch', async () => {
    const data = libraryFixture()
    const { rerender } = render(<LibraryBrowser data={{ ...data, episodes: [] }} onChanged={vi.fn()} />)
    expect(screen.getByText(/Nothing to review yet/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Make a batch →' })).toHaveAttribute('href', '#/studio/make')
    rerender(<LibraryBrowser data={{ ...data, episodes: data.episodes.filter((e) => e.status === 'approved') }} onChanged={vi.fn()} />)
    expect(screen.getByText(/Nothing to review\. 1 approved: they are ready for the Schedule\./)).toBeInTheDocument()
  })
})
