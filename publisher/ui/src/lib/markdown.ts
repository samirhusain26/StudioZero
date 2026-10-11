/**
 * A tiny Markdown subset parser (REBUILD_CONTRACTS.md §4). It produces a plain data tree that
 * components/Markdown.tsx renders as React elements; nothing is ever inserted as HTML.
 *
 * Supported: `#`–`###` headings, paragraphs, `-`/`*`/`1.` lists (flat), fenced code, inline code,
 * `**bold**`, `[text](url)` links (only `#anchor` and `https:` targets; anything else renders as
 * its text) and pipe tables. Raw HTML is shown as literal text, except whole-line HTML comments
 * (`<!-- … -->`), which are dropped. Backslash escapes a punctuation character.
 */

export type Inline =
  | { type: 'text'; text: string }
  | { type: 'code'; text: string }
  | { type: 'bold'; children: Inline[] }
  | { type: 'link'; href: string; children: Inline[] }

export type Block =
  | { type: 'heading'; level: 1 | 2 | 3; text: string; children: Inline[]; anchor: string }
  | { type: 'paragraph'; children: Inline[] }
  | { type: 'list'; ordered: boolean; start: number; items: Inline[][] }
  | { type: 'code'; lang: string; text: string }
  | { type: 'table'; header: Inline[][]; rows: Inline[][][] }

/** Heading anchor: lowercase, every run of non-alphanumerics becomes `-`, trimmed of `-`. */
export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

/** Only in-guide anchors and https URLs are links; everything else is shown as plain text. */
export function safeHref(url: string): string | null {
  const trimmed = url.trim()
  if (/^#[a-z0-9]+(?:-[a-z0-9]+)*$/.test(trimmed)) return trimmed
  if (/^https:\/\/[^\s<>"']+$/i.test(trimmed)) {
    try {
      return new URL(trimmed).protocol === 'https:' ? trimmed : null
    } catch {
      return null
    }
  }
  return null
}

function pushText(out: Inline[], text: string) {
  if (!text) return
  const last = out[out.length - 1]
  if (last && last.type === 'text') last.text += text
  else out.push({ type: 'text', text })
}

/** Plain text of inline nodes (for heading slugs and tests). */
export function inlineText(nodes: Inline[]): string {
  return nodes.map((n) => (n.type === 'text' || n.type === 'code' ? n.text : inlineText(n.children))).join('')
}

export function parseInline(src: string): Inline[] {
  const out: Inline[] = []
  let i = 0
  while (i < src.length) {
    const ch = src[i] as string
    if (ch === '\\' && i + 1 < src.length && /[\\`*_[\]()#|!-]/.test(src[i + 1] as string)) {
      pushText(out, src[i + 1] as string)
      i += 2
      continue
    }
    if (ch === '`') {
      const end = src.indexOf('`', i + 1)
      if (end > i) {
        out.push({ type: 'code', text: src.slice(i + 1, end) })
        i = end + 1
        continue
      }
    }
    if (ch === '*' && src[i + 1] === '*') {
      const end = src.indexOf('**', i + 2)
      if (end > i + 2) {
        out.push({ type: 'bold', children: parseInline(src.slice(i + 2, end)) })
        i = end + 2
        continue
      }
    }
    if (ch === '[') {
      const close = findClose(src, i)
      if (close > i && src[close + 1] === '(') {
        const end = src.indexOf(')', close + 2)
        if (end > close) {
          const children = parseInline(src.slice(i + 1, close))
          const href = safeHref(src.slice(close + 2, end))
          if (href) out.push({ type: 'link', href, children })
          else
            for (const child of children) {
              if (child.type === 'text') pushText(out, child.text)
              else out.push(child)
            }
          i = end + 1
          continue
        }
      }
    }
    pushText(out, ch)
    i++
  }
  return out
}

/** Index of the `]` matching the `[` at `open` (nested brackets allowed), or -1. */
function findClose(src: string, open: number): number {
  let depth = 0
  for (let j = open; j < src.length; j++) {
    if (src[j] === '\\') {
      j++
      continue
    }
    if (src[j] === '[') depth++
    else if (src[j] === ']' && --depth === 0) return j
  }
  return -1
}

const FENCE = /^\s*(```+|~~~+)\s*([\w-]*)\s*$/
const HEADING = /^(#{1,3})\s+(.*?)\s*#*\s*$/
const UL = /^\s*[-*+]\s+(.*)$/
const OL = /^\s*(\d+)[.)]\s+(.*)$/
const TABLE_SEP = /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/
const COMMENT_START = /^\s*<!--/

function splitRow(line: string): string[] {
  let body = line.trim()
  if (body.startsWith('|')) body = body.slice(1)
  if (body.endsWith('|') && !body.endsWith('\\|')) body = body.slice(0, -1)
  const cells: string[] = []
  let cell = ''
  for (let i = 0; i < body.length; i++) {
    const ch = body[i] as string
    if (ch === '\\' && body[i + 1] === '|') {
      cell += '|'
      i++
    } else if (ch === '|') {
      cells.push(cell.trim())
      cell = ''
    } else cell += ch
  }
  cells.push(cell.trim())
  return cells
}

function startsBlock(line: string, next: string | undefined): boolean {
  return (
    FENCE.test(line) ||
    HEADING.test(line) ||
    UL.test(line) ||
    OL.test(line) ||
    COMMENT_START.test(line) ||
    (line.trim().startsWith('|') && next !== undefined && TABLE_SEP.test(next))
  )
}

/** Parse Markdown into blocks. Heading anchors are slugs; `assignAnchors` makes them unique. */
export function parseMarkdown(src: string): Block[] {
  const lines = src.replace(/\r\n?/g, '\n').split('\n')
  const blocks: Block[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i] as string
    if (!line.trim()) {
      i++
      continue
    }
    if (COMMENT_START.test(line)) {
      while (i < lines.length && !(lines[i] as string).includes('-->')) i++
      i++
      continue
    }
    const fence = FENCE.exec(line)
    if (fence) {
      const marker = (fence[1] as string).slice(0, 3)
      const body: string[] = []
      i++
      while (i < lines.length && !(lines[i] as string).trim().startsWith(marker)) body.push(lines[i++] as string)
      i++
      blocks.push({ type: 'code', lang: fence[2] ?? '', text: body.join('\n') })
      continue
    }
    const heading = HEADING.exec(line)
    if (heading) {
      const text = heading[2] ?? ''
      const children = parseInline(text)
      blocks.push({ type: 'heading', level: (heading[1] as string).length as 1 | 2 | 3, text: inlineText(children), children, anchor: slugify(inlineText(children)) })
      i++
      continue
    }
    if (line.trim().startsWith('|') && i + 1 < lines.length && TABLE_SEP.test(lines[i + 1] as string)) {
      const header = splitRow(line).map(parseInline)
      i += 2
      const rows: Inline[][][] = []
      while (i < lines.length && (lines[i] as string).trim().startsWith('|')) rows.push(splitRow(lines[i++] as string).map(parseInline))
      blocks.push({ type: 'table', header, rows })
      continue
    }
    const ul = UL.exec(line)
    const ol = OL.exec(line)
    if (ul || ol) {
      const ordered = !ul
      const start = ol ? Number(ol[1]) : 1
      const items: string[] = []
      while (i < lines.length) {
        const current = lines[i] as string
        const item = ordered ? OL.exec(current) : UL.exec(current)
        if (item) {
          items.push((ordered ? item[2] : item[1]) ?? '')
          i++
        } else if (current.trim() && /^\s+/.test(current) && items.length && !startsBlock(current, lines[i + 1])) {
          items[items.length - 1] += ` ${current.trim()}`
          i++
        } else break
      }
      blocks.push({ type: 'list', ordered, start, items: items.map(parseInline) })
      continue
    }
    const para: string[] = []
    while (i < lines.length && (lines[i] as string).trim() && (para.length === 0 || !startsBlock(lines[i] as string, lines[i + 1]))) {
      para.push((lines[i] as string).trim())
      i++
    }
    blocks.push({ type: 'paragraph', children: parseInline(para.join(' ')) })
  }
  return blocks
}

/**
 * Make heading anchors unique across several documents (in order): the first keeps its slug,
 * later duplicates get `-2`, `-3`, …. Returns new block lists; the inputs are not changed.
 */
export function assignAnchors(docs: Block[][]): Block[][] {
  const seen = new Map<string, number>()
  return docs.map((blocks) =>
    blocks.map((block) => {
      if (block.type !== 'heading') return block
      const base = block.anchor || 'section'
      const count = (seen.get(base) ?? 0) + 1
      seen.set(base, count)
      return { ...block, anchor: count === 1 ? base : `${base}-${count}` }
    }),
  )
}

/** Every `#anchor` link target in the blocks (for link checks). */
export function linkTargets(blocks: Block[]): string[] {
  const out: string[] = []
  const walk = (nodes: Inline[]) => {
    for (const n of nodes) {
      if (n.type === 'link') {
        out.push(n.href)
        walk(n.children)
      } else if (n.type === 'bold') walk(n.children)
    }
  }
  for (const b of blocks) {
    if (b.type === 'heading' || b.type === 'paragraph') walk(b.children)
    else if (b.type === 'list') b.items.forEach(walk)
    else if (b.type === 'table') [b.header, ...b.rows].forEach((row) => row.forEach(walk))
  }
  return out
}
