import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { parseMarkdown } from '../lib/markdown'
import { Markdown, MarkdownBlocks } from './Markdown'

describe('Markdown renderer', () => {
  it('never turns text into HTML', () => {
    const { container } = render(
      <Markdown source={'# Hi <b>there</b>\n\n<script>alert(1)</script>\n\n<img src=x onerror="alert(2)">\n\n[x](javascript:alert(3)) [y](data:text/html,z)'} />,
    )
    expect(container.querySelector('script')).toBeNull()
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
    expect(container.textContent).toContain('<script>alert(1)</script>')
    expect(container.textContent).toContain('<img src=x onerror="alert(2)">')
    for (const a of container.querySelectorAll('a')) expect(a.getAttribute('href')).toMatch(/^(#\/guide\/|https:)/)
    expect(container.querySelectorAll('a')).toHaveLength(0)
  })

  it('renders #anchor links as guide routes and https links in a new tab', () => {
    render(<Markdown source="See [Health](#health) or [docs](https://example.com/docs)." />)
    expect(screen.getByRole('link', { name: 'Health' })).toHaveAttribute('href', '#/guide/health')
    const external = screen.getByRole('link', { name: 'docs' })
    expect(external).toHaveAttribute('href', 'https://example.com/docs')
    expect(external).toHaveAttribute('target', '_blank')
    expect(external.getAttribute('rel')).toContain('noopener')
  })

  it('renders headings one level below the page title, with guide ids when asked', () => {
    render(<MarkdownBlocks blocks={parseMarkdown('# Update the Pi\n## Rollback\n### Detail')} withIds />)
    expect(screen.getByRole('heading', { level: 2, name: 'Update the Pi' })).toHaveAttribute('id', 'guide-update-the-pi')
    expect(screen.getByRole('heading', { level: 3, name: 'Rollback' })).toHaveAttribute('id', 'guide-rollback')
    expect(screen.getByRole('heading', { level: 4, name: 'Detail' })).toBeInTheDocument()
  })

  it('renders lists, code and tables', () => {
    const { container } = render(<Markdown source={'1. a\n2. b\n\n```\ncode <x>\n```\n\n| A | B |\n|---|---|\n| 1 | 2 |'} />)
    expect(container.querySelectorAll('ol li')).toHaveLength(2)
    expect(container.querySelector('pre code')?.textContent).toBe('code <x>')
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getAllByRole('columnheader').map((th) => th.textContent)).toEqual(['A', 'B'])
  })
})
