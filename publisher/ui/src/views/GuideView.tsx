import { useEffect } from 'react'
import { api } from '../api/client'
import { headingDomId, MarkdownBlocks } from '../components/Markdown'
import { useApi } from '../hooks/useApi'
import { shortHash } from '../lib/format'
import { GUIDE, hasAnchor, type Guide } from '../lib/guide'
import { guideHash } from '../views'

function scrollToHeading(anchor: string) {
  const el = document.getElementById(headingDomId(anchor))
  if (!el) return
  if (typeof el.scrollIntoView === 'function') el.scrollIntoView({ block: 'start' })
  el.focus({ preventScroll: true })
}

export function GuideView({ anchor, guide = GUIDE }: { anchor?: string | undefined; guide?: Guide }) {
  const update = useApi(() => api.updateStatus())
  const running = update.data?.runningCommit ?? null

  useEffect(() => {
    if (anchor) requestAnimationFrame(() => scrollToHeading(anchor))
  }, [anchor])

  const toc = guide.headings.filter((h) => h.level <= 2)
  return (
    <div className="stack-lg guide">
      <p className="muted" data-testid="guide-meta">
        Guide updated {guide.meta.updated} · running {running ? <code>{shortHash(running, 7)}</code> : update.loading ? '…' : 'unknown'}
      </p>
      {anchor && !hasAnchor(guide, anchor) ? (
        <p className="notice notice-warn" role="alert">
          There is no guide section “{anchor}”. Pick one from the contents below.
        </p>
      ) : null}
      <nav className="card guide-toc" aria-labelledby="guide-toc-h">
        <h2 id="guide-toc-h">Contents</h2>
        <ol className="toc-list">
          {toc.map((h) => (
            <li key={h.anchor} className={h.level === 1 ? 'toc-top' : 'toc-sub'}>
              <a href={guideHash(h.anchor)} onClick={() => scrollToHeading(h.anchor)}>
                {h.text}
              </a>
            </li>
          ))}
        </ol>
      </nav>
      {guide.docs.map((doc) => (
        <article key={doc.name} className="card guide-doc" aria-label={guide.headings.find((h) => h.doc === doc.name)?.text ?? doc.name}>
          <MarkdownBlocks blocks={doc.blocks} withIds />
        </article>
      ))}
    </div>
  )
}
