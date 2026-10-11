import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { draftResponse } from '../../test/fixtures'
import { ApprovalPanel } from './ApprovalPanel'
import { DraftPreview } from './DraftPreview'

describe('ApprovalPanel', () => {
  it('approves with one tap, sending the server phrase; there is no typed field', async () => {
    const onApprove = vi.fn()
    const user = userEvent.setup()
    render(<ApprovalPanel draft={draftResponse()} pendingRequest={null} lastResult={null} zone="America/New_York" busy={false} error={null} onApprove={onApprove} />)
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    expect(screen.getByText('Approving deploys and checks the media, then publishing starts automatically.')).toBeInTheDocument()
    const button = screen.getByRole('button', { name: 'Approve schedule' })
    expect(button).toBeEnabled()
    await user.click(button)
    expect(onApprove).toHaveBeenCalledWith('APPROVE ab12cd34')
  })

  it('stays disabled while blocking problems exist or another approval is pending', () => {
    const { unmount } = render(
      <ApprovalPanel
        draft={draftResponse({ blockingProblems: ['The library changed since this draft'] })}
        pendingRequest={null}
        lastResult={null}
        zone="America/New_York"
        busy={false}
        error={null}
        onApprove={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: 'Approve schedule' })).toBeDisabled()
    unmount()
    render(
      <ApprovalPanel
        draft={draftResponse()}
        pendingRequest={{ draftSha256: 'f'.repeat(64), requestedAt: '2026-10-10T12:00:00Z' }}
        lastResult={null}
        zone="America/New_York"
        busy={false}
        error={null}
        onApprove={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: 'Approve schedule' })).toBeDisabled()
  })
})

describe('DraftPreview', () => {
  it('shows local and UTC times, nested companions, exclusions and the fill summary', () => {
    render(<DraftPreview draft={draftResponse()} previousSha={null} busy={false} onEdit={vi.fn()} onRemove={vi.fn()} onRegenerate={vi.fn()} />)
    expect(screen.getByTestId('draft-summary')).toHaveTextContent('1 of 2 requested slots fillable')
    expect(screen.getByText('Mon 12 Oct, 09:00 EDT · 13:00 UTC')).toBeInTheDocument()
    expect(screen.getByText('Mon 12 Oct, 09:02 EDT · 13:02 UTC')).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'Companion jobs' })).toHaveTextContent('comment your letter')
    expect(screen.getByText('Blocked: Buffer reconnect pending', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('Monday, 12 October 2026')).toBeInTheDocument()
  })
})
