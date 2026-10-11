import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { ChannelSummary, Platform } from '../../api/types'
import { GeneratorForm } from './GeneratorForm'

const channel = (platform: Platform, blockedReason: string | null = null): ChannelSummary => ({
  platform,
  accountId: 'acct',
  route: 'buffer',
  enabled: blockedReason === null,
  identityVerified: true,
  publishingVerified: true,
  blockedReason,
  profileUrl: null,
})

describe('GeneratorForm recommended schedule', () => {
  it('starts empty, fills the recommended cadence on tap and leaves blocked platforms out', async () => {
    const onGenerate = vi.fn()
    const channels = [channel('threads'), channel('instagram'), channel('tiktok', 'Disconnected in Buffer')]
    render(<GeneratorForm channels={channels} busy={false} onGenerate={onGenerate} />)
    expect(screen.getByLabelText('Timezone (IANA name)')).toHaveValue('')
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: 'Use recommended schedule' }))
    expect(screen.getByLabelText('Timezone (IANA name)')).toHaveValue('America/New_York')
    expect(screen.getByLabelText('Include Threads')).toBeChecked()
    expect(screen.getByRole('list', { name: 'Threads times' })).toHaveTextContent('09:00')
    expect(screen.getByRole('list', { name: 'Instagram times' })).toHaveTextContent('18:00')
    expect(screen.getByLabelText('Include TikTok')).not.toBeChecked()
    await user.click(screen.getByRole('button', { name: 'Generate draft' }))
    expect(onGenerate).toHaveBeenCalledTimes(1)
    expect(Object.keys(onGenerate.mock.calls[0]?.[0].platforms).sort()).toEqual(['bluesky', 'facebook', 'instagram', 'threads', 'x', 'youtube'])
  })
})
