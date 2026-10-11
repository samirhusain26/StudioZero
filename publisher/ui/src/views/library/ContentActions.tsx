import { useState } from 'react'
import { api } from '../../api/client'
import type { LibraryActionResponse, LibraryEpisode } from '../../api/types'
import { ErrorNotice } from '../../components/ErrorNotice'
import { ConfirmDialog } from '../../components/Modal'
import { readReviewer, writeReviewer } from '../../lib/libraryList'

export type ContentAction = 'approve' | 'withdraw' | 'delete'

interface Pending {
  action: ContentAction
  items: LibraryEpisode[]
}

function summarize(verb: string, response: LibraryActionResponse): string {
  const ok = response.results.filter((r) => r.ok).length
  const refused = response.results.filter((r) => !r.ok)
  return `${verb} ${ok} of ${response.results.length}.${refused.length ? ` Refused: ${refused.map((r) => `${r.episodeId} (${r.message ?? 'refused'})`).join('; ')}.` : ''}`
}

/**
 * Approve / withdraw / delete with the existing confirmations. Approval records the reviewer named in the
 * dialog with the current file, metadata and caption hashes (the approval of record, server side).
 */
export function useContentActions(onChanged: () => void) {
  const [pending, setPending] = useState<Pending | null>(null)
  const [reviewer, setReviewer] = useState(readReviewer)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [error, setError] = useState<unknown>(null)
  const reviewerOk = reviewer.trim().length > 0

  const run = async () => {
    if (!pending) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const items = pending.items.map((e) => ({ episodeId: e.episodeId, revision: e.revision }))
      if (pending.action === 'approve') {
        writeReviewer(reviewer.trim())
        setResult(summarize('Approved', await api.approveContent({ items, reviewer: reviewer.trim() })))
      } else if (pending.action === 'withdraw') setResult(summarize('Withdrew', await api.withdrawContent({ items, reviewer: reviewer.trim() })))
      else {
        const first = pending.items[0]
        if (first) {
          await api.deleteEpisode(first.episodeId, first.revision)
          setResult(`Deleted ${first.episodeId} rev ${first.revision}.`)
        }
      }
      onChanged()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
      setPending(null)
    }
  }

  const ask = (action: ContentAction, items: LibraryEpisode[]) => {
    setResult(null)
    setPending({ action, items })
  }

  const status = (
    <>
      <div aria-live="polite" role="status">
        {result ? <p className="notice notice-info">{result}</p> : null}
      </div>
      <ErrorNotice error={error} title="Action failed" />
    </>
  )

  const dialog = pending ? (
    <ConfirmDialog
      title={
        pending.action === 'approve'
          ? `Approve ${pending.items.length} video${pending.items.length === 1 ? '' : 's'}?`
          : pending.action === 'withdraw'
            ? 'Withdraw approval?'
            : 'Delete this upload?'
      }
      confirmLabel={pending.action === 'approve' ? 'Approve' : pending.action === 'withdraw' ? 'Withdraw' : 'Delete permanently'}
      danger={pending.action !== 'approve'}
      busy={busy}
      disabled={pending.action !== 'delete' && !reviewerOk}
      onConfirm={() => void run()}
      onCancel={() => setPending(null)}
    >
      {pending.action === 'delete' ? null : (
        <div className="field">
          <label htmlFor="reviewer">Reviewer name</label>
          <input id="reviewer" type="text" value={reviewer} onChange={(e) => setReviewer(e.target.value)} autoComplete="name" />
          <p className="hint">Recorded with the decision (the approval of record).</p>
        </div>
      )}
      {pending.action === 'approve' ? (
        <p>
          Records {reviewer.trim() || '(no reviewer)'} as having reviewed the content, rights and captions of these exact files. Approval does
          not schedule anything.
        </p>
      ) : pending.action === 'withdraw' ? (
        <p>The video will not be offered to new schedules. An already approved schedule is not changed.</p>
      ) : (
        <p>The upload was never in an approved manifest, so it can be removed. This cannot be undone.</p>
      )}
      <ul>
        {pending.items.slice(0, 20).map((e) => (
          <li key={`${e.episodeId}@${e.revision}`}>
            {e.episodeId} rev {e.revision}
          </li>
        ))}
        {pending.items.length > 20 ? <li>…and {pending.items.length - 20} more</li> : null}
      </ul>
    </ConfirmDialog>
  ) : null

  return { ask, dialog, status }
}
