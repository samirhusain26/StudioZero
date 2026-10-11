import { describe, expect, it } from 'vitest'
import { assignAnchors, inlineText, linkTargets, parseInline, parseMarkdown, safeHref, slugify } from './markdown'

describe('slugify', () => {
  it('lowercases, turns runs of non-alphanumerics into one dash and trims', () => {
    expect(slugify('Things only Samir can do')).toBe('things-only-samir-can-do')
    expect(slugify('Update the Pi')).toBe('update-the-pi')
    expect(slugify('  What’s new?  (v2) ')).toBe('what-s-new-v2')
    expect(slugify('--Glossary--')).toBe('glossary')
    expect(slugify('Unit files changed')).toBe('unit-files-changed')
  })
})

describe('safeHref', () => {
  it('allows only #anchors and https URLs', () => {
    expect(safeHref('#upload-a-batch')).toBe('#upload-a-batch')
    expect(safeHref('https://example.com/a?b=c')).toBe('https://example.com/a?b=c')
    expect(safeHref('javascript:alert(1)')).toBeNull()
    expect(safeHref('http://example.com')).toBeNull()
    expect(safeHref('data:text/html,<b>x</b>')).toBeNull()
    expect(safeHref('#/library')).toBeNull()
    expect(safeHref('//evil.example')).toBeNull()
    expect(safeHref('https://x" onmouseover="y')).toBeNull()
  })
})

describe('parseInline', () => {
  it('parses code, bold and links', () => {
    expect(parseInline('Run `npm test` **now** and see [the guide](#health).')).toEqual([
      { type: 'text', text: 'Run ' },
      { type: 'code', text: 'npm test' },
      { type: 'text', text: ' ' },
      { type: 'bold', children: [{ type: 'text', text: 'now' }] },
      { type: 'text', text: ' and see ' },
      { type: 'link', href: '#health', children: [{ type: 'text', text: 'the guide' }] },
      { type: 'text', text: '.' },
    ])
  })

  it('renders disallowed links as their text only', () => {
    expect(parseInline('[click](javascript:alert(1))')).toEqual([{ type: 'text', text: 'click)' }])
    expect(inlineText(parseInline('[plain](http://insecure.example)'))).toBe('plain')
  })

  it('keeps raw HTML as literal text', () => {
    expect(parseInline('<img src=x onerror=alert(1)>')).toEqual([{ type: 'text', text: '<img src=x onerror=alert(1)>' }])
  })

  it('honours backslash escapes', () => {
    expect(inlineText(parseInline('2 \\* 3 = 6 and \\`x\\`'))).toBe('2 * 3 = 6 and `x`')
  })
})

describe('parseMarkdown', () => {
  it('parses headings, paragraphs, lists, code, tables and drops HTML comments', () => {
    const blocks = parseMarkdown(
      [
        '<!-- PLACEHOLDER: replaced by the guide builder -->',
        '# Upload a batch',
        '',
        'First line',
        'continues here.',
        '',
        '- one',
        '- two',
        '  wrapped',
        '',
        '3. third',
        '4. fourth',
        '',
        '```bash',
        'sudo do-thing <arg>',
        '```',
        '',
        '| Key | Value |',
        '|-----|:-----:|',
        '| a | `b` |',
        '## Failed upload',
      ].join('\n'),
    )
    expect(blocks.map((b) => b.type)).toEqual(['heading', 'paragraph', 'list', 'list', 'code', 'table', 'heading'])
    expect(blocks[0]).toMatchObject({ level: 1, text: 'Upload a batch', anchor: 'upload-a-batch' })
    expect(blocks[1]).toEqual({ type: 'paragraph', children: [{ type: 'text', text: 'First line continues here.' }] })
    expect(blocks[2]).toMatchObject({ ordered: false, items: [[{ text: 'one' }], [{ text: 'two wrapped' }]] })
    expect(blocks[3]).toMatchObject({ ordered: true, start: 3 })
    expect(blocks[4]).toEqual({ type: 'code', lang: 'bash', text: 'sudo do-thing <arg>' })
    expect(blocks[5]).toMatchObject({ type: 'table', header: [[{ text: 'Key' }], [{ text: 'Value' }]], rows: [[[{ text: 'a' }], [{ type: 'code', text: 'b' }]]] })
    expect(blocks[6]).toMatchObject({ level: 2, anchor: 'failed-upload' })
  })

  it('makes duplicate anchors unique across documents', () => {
    const docs = assignAnchors([parseMarkdown('# Recovery\n## Notes'), parseMarkdown('# Notes')])
    const anchors = docs.flat().flatMap((b) => (b.type === 'heading' ? [b.anchor] : []))
    expect(anchors).toEqual(['recovery', 'notes', 'notes-2'])
  })

  it('lists link targets', () => {
    expect(linkTargets(parseMarkdown('See [a](#x) and **[b](#y)**.\n\n- [c](https://e.example)'))).toEqual(['#x', '#y', 'https://e.example'])
  })
})
