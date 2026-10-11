import { useState } from 'react'
import { api } from '../../api/client'
import type { CleanupPreview } from '../../api/types'
import { ErrorNotice } from '../../components/ErrorNotice'
import { ConfirmDialog } from '../../components/Modal'
import { formatBytes, platformName } from '../../lib/format'

/** Frees space by removing videos that are fully posted; covers, records and history stay. */
export function RemovePostedVideos({ onChanged }: { onChanged: () => void }) {
  const [preview, setPreview] = useState<CleanupPreview | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [result, setResult] = useState<string | null>(null)

  const open = async () => {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      setPreview(await api.cleanupPreview())
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    if (!preview) return
    setBusy(true)
    try {
      const done = await api.removePostedVideos(preview.candidates.map((c) => c.videoSha256))
      const kept = done.refused.length ? ` ${done.refused.length} changed since the list was shown and were kept.` : ''
      setResult(`Removed ${done.removed.length} video${done.removed.length === 1 ? '' : 's'}, freed ${formatBytes(done.bytesFreed)}.${kept}`)
      setPreview(null)
      onChanged()
    } catch (e) {
      setError(e)
      setPreview(null)
    } finally {
      setBusy(false)
    }
  }

  const count = preview?.candidates.length ?? 0
  return (
    <section className="card stack" aria-labelledby="cleanup-h">
      <h2 id="cleanup-h">Free space</h2>
      <p className="hint">
        Removes videos whose posts have all finished and that no approved post still needs. Covers, episode records, stats and history stay. A
        removed video cannot be scheduled again (for example to a platform added later) until you upload the same file again.
      </p>
      <div className="actions">
        <button type="button" className="btn" onClick={() => void open()} disabled={busy}>
          {busy && !preview ? 'Checking…' : 'Remove posted videos…'}
        </button>
      </div>
      <div aria-live="polite" role="status">
        {result ? <p className="notice notice-info">{result}</p> : null}
      </div>
      <ErrorNotice error={error} title="Could not remove videos" />
      {preview ? (
        <ConfirmDialog
          title={count ? `Remove ${count} posted video${count === 1 ? '' : 's'}?` : 'Nothing to remove'}
          confirmLabel={`Remove and free ${formatBytes(preview.totalBytes)}`}
          onConfirm={() => void remove()}
          onCancel={() => setPreview(null)}
          busy={busy}
          disabled={count === 0 || preview.blockedReason !== null}
          danger
        >
          {preview.blockedReason ? <p className="notice notice-warn">{preview.blockedReason}</p> : null}
          {count === 0 ? (
            <p>No video is ready to remove: each one still has a post waiting, sending or needing review, or has not been posted yet.</p>
          ) : (
            <>
              <p>
                These videos have finished posting. Their covers and records stay; the files are deleted from the Pi and leave the public media site
                at the next schedule approval.
              </p>
              <ul className="compact-list">
                {preview.candidates.map((c) => (
                  <li key={c.videoSha256}>
                    {c.episodes.map((e) => `${e.episodeId} rev ${e.revision}`).join(', ') || c.videoSha256.slice(0, 12)} · posted on{' '}
                    {c.postedOn.map(platformName).join(', ')} · {formatBytes(c.bytes)}
                  </li>
                ))}
              </ul>
            </>
          )}
        </ConfirmDialog>
      ) : null}
    </section>
  )
}
