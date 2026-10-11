import { useMemo, type ReactNode } from 'react'
import { parseMarkdown, type Block, type Inline } from '../lib/markdown'
import { guideHash } from '../views'

/** DOM id of a guide heading (prefixed so a heading can never collide with an app element id). */
export function headingDomId(anchor: string): string {
  return `guide-${anchor}`
}

function renderInline(nodes: Inline[], keyPrefix: string): ReactNode[] {
  return nodes.map((node, i) => {
    const key = `${keyPrefix}-${i}`
    switch (node.type) {
      case 'text':
        return node.text
      case 'code':
        return <code key={key}>{node.text}</code>
      case 'bold':
        return <strong key={key}>{renderInline(node.children, key)}</strong>
      case 'link':
        return node.href.startsWith('#') ? (
          <a key={key} href={guideHash(node.href.slice(1))}>
            {renderInline(node.children, key)}
          </a>
        ) : (
          <a key={key} href={node.href} target="_blank" rel="noopener noreferrer">
            {renderInline(node.children, key)}
          </a>
        )
    }
  })
}

function HeadingTag({ level, children, id }: { level: number; children: ReactNode; id?: string }) {
  const props = id ? { id, tabIndex: -1 } : {}
  if (level <= 2) return <h2 {...props}>{children}</h2>
  if (level === 3) return <h3 {...props}>{children}</h3>
  return <h4 {...props}>{children}</h4>
}

/**
 * Renders the Markdown subset from lib/markdown.ts as React elements (never as HTML).
 * `#` headings render one level below the page title (h2); `withIds` gives headings their
 * guide anchors so `#/guide/<anchor>` can scroll to them.
 */
export function MarkdownBlocks({ blocks, withIds = false }: { blocks: Block[]; withIds?: boolean }) {
  return (
    <div className="markdown">
      {blocks.map((block, i) => {
        const key = `b${i}`
        switch (block.type) {
          case 'heading':
            return (
              <HeadingTag key={key} level={block.level + 1} {...(withIds ? { id: headingDomId(block.anchor) } : {})}>
                {renderInline(block.children, key)}
              </HeadingTag>
            )
          case 'paragraph':
            return <p key={key}>{renderInline(block.children, key)}</p>
          case 'list': {
            const items = block.items.map((item, j) => <li key={`${key}-${j}`}>{renderInline(item, `${key}-${j}`)}</li>)
            return block.ordered ? (
              <ol key={key} {...(block.start !== 1 ? { start: block.start } : {})}>
                {items}
              </ol>
            ) : (
              <ul key={key}>{items}</ul>
            )
          }
          case 'code':
            return (
              <pre key={key} className="md-code">
                <code>{block.text}</code>
              </pre>
            )
          case 'table':
            return (
              <div key={key} className="table-wrap md-table">
                <table>
                  <thead>
                    <tr>
                      {block.header.map((cell, j) => (
                        <th key={j} scope="col">
                          {renderInline(cell, `${key}-h${j}`)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, r) => (
                      <tr key={r}>
                        {row.map((cell, j) => (
                          <td key={j}>{renderInline(cell, `${key}-${r}-${j}`)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
        }
      })}
    </div>
  )
}

/** Parse and render Markdown text (e.g. a batch BRIEF.md / RETRO.md). */
export function Markdown({ source }: { source: string }) {
  const blocks = useMemo(() => parseMarkdown(source), [source])
  return <MarkdownBlocks blocks={blocks} />
}
