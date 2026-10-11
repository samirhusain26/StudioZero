import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RemovePostedVideos } from './RemovePostedVideos'

const { api } = vi.hoisted(() => ({ api: { cleanupPreview: vi.fn(), removePostedVideos: vi.fn() } }))
vi.mock('../../api/client', async (importOriginal) => ({ ...(await importOriginal<typeof import('../../api/client')>()), api }))

const sha = 'a'.repeat(64)

describe('RemovePostedVideos', () => {
  beforeEach(() => {
    api.cleanupPreview.mockReset()
    api.removePostedVideos.mockReset()
  })

  it('previews, then removes exactly the listed videos and reports the space freed', async () => {
    api.cleanupPreview.mockResolvedValue({
      candidates: [{ videoSha256: sha, bytes: 21_000_000, episodes: [{ episodeId: 'scalar-clues-001', revision: 1, batchId: 'b', game: 'scalar' }], postedOn: ['instagram', 'x'] }],
      totalBytes: 21_000_000,
      blockedReason: null,
    })
    api.removePostedVideos.mockResolvedValue({ removed: [sha], refused: [], bytesFreed: 21_000_000 })
    const onChanged = vi.fn()
    const user = userEvent.setup()
    render(<RemovePostedVideos onChanged={onChanged} />)
    await user.click(screen.getByRole('button', { name: 'Remove posted videos…' }))
    expect(await screen.findByText(/scalar-clues-001 rev 1 · posted on Instagram, X · 21 MB/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Remove and free 21 MB' }))
    expect(api.removePostedVideos).toHaveBeenCalledWith([sha])
    expect(await screen.findByText('Removed 1 video, freed 21 MB.')).toBeInTheDocument()
    expect(onChanged).toHaveBeenCalled()
  })

  it('cannot confirm when nothing is ready or an approval is running', async () => {
    api.cleanupPreview.mockResolvedValue({ candidates: [], totalBytes: 0, blockedReason: 'A schedule approval is being processed; wait for it to finish.' })
    const user = userEvent.setup()
    render(<RemovePostedVideos onChanged={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: 'Remove posted videos…' }))
    expect(await screen.findByText(/A schedule approval is being processed/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Remove and free/ })).toBeDisabled()
    expect(api.removePostedVideos).not.toHaveBeenCalled()
  })
})
