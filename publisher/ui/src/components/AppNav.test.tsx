import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { AppNav } from './AppNav'
import { StepLine } from './StepLine'

describe('AppNav', () => {
  it('renders the five sections in order, marks the current one and navigates by path', async () => {
    const onNavigate = vi.fn()
    render(<AppNav current="schedule" version="abc1234" onNavigate={onNavigate} />)
    const nav = screen.getByRole('navigation', { name: 'Sections' })
    const links = within(nav).getAllByRole('link')
    expect(links.map((l) => l.textContent)).toEqual(['⌂Home', '▣Library', '▦Schedule', '≡Activity', '⚙︎Settings'])
    expect(within(nav).getByRole('link', { name: 'Schedule' })).toHaveAttribute('aria-current', 'page')
    expect(within(nav).getByRole('link', { name: 'Home' })).not.toHaveAttribute('aria-current')
    expect(within(nav).getByRole('link', { name: 'Library' })).toHaveAttribute('href', '#/library')
    expect(nav).toHaveTextContent('v abc1234')
    await userEvent.setup().click(within(nav).getByRole('link', { name: 'Activity' }))
    expect(onNavigate).toHaveBeenCalledWith('activity')
  })
})

describe('StepLine', () => {
  it('says which step of six a screen is, with its state', () => {
    const { rerender } = render(<StepLine step={{ n: 3, label: 'Review', state: 'current' }} />)
    expect(screen.getByTestId('step-line')).toHaveTextContent('Step 3 of 6 · Review · your next step')
    rerender(<StepLine step={{ n: 5, label: 'Post', state: 'blocked' }} />)
    expect(screen.getByTestId('step-line')).toHaveTextContent('Step 5 of 6 · Post · blocked')
    rerender(<StepLine step={{ n: 4, label: 'Schedule', state: 'todo' }} />)
    expect(screen.getByTestId('step-line')).toHaveTextContent(/^Step 4 of 6 · Schedule$/)
    rerender(<StepLine step={null} />)
    expect(screen.queryByTestId('step-line')).toBeNull()
  })
})
