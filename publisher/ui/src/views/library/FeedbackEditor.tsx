import { useId, useState } from 'react'
import { api } from '../../api/client'
import type { EpisodeFeedback, FeedbackTag } from '../../api/types'
import { FEEDBACK_TAGS } from '../../api/types'
import { ErrorNotice } from '../../components/ErrorNotice'
import { ConfirmDialog } from '../../components/Modal'
import { TextCounterField } from '../../components/TextCounterField'
import { Time } from '../../components/Time'
import { codePoints, counter } from '../../lib/contract'
import { FEEDBACK_NOTE_LIMIT, TAG_LABELS } from '../../lib/nextBatch'

function sameTags(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && [...a].sort().join() === [...b].sort().join()
}

export function FeedbackEditor({
  episodeId,
  revision,
  initial,
  zone,
}: {
  episodeId: string
  revision: number
  initial: EpisodeFeedback | null
  zone: string
}) {
  const id = useId()
  const [saved, setSaved] = useState<EpisodeFeedback | null>(initial)
  const [tags, setTags] = useState<FeedbackTag[]>(initial?.tags ?? [])
  const [note, setNote] = useState(initial?.note ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [message, setMessage] = useState('')
  const [confirmClear, setConfirmClear] = useState(false)

  const noteCounter = counter(codePoints(note), FEEDBACK_NOTE_LIMIT)
  const dirty = !sameTags(tags, saved?.tags ?? []) || note !== (saved?.note ?? '')
  const empty = tags.length === 0 && note.trim() === ''
  const canSave = dirty && !empty && !noteCounter.over && !busy

  const toggle = (tag: FeedbackTag) => {
    setMessage('')
    setTags((current) => (current.includes(tag) ? current.filter((t) => t !== tag) : FEEDBACK_TAGS.filter((t) => t === tag || current.includes(t))))
  }

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      const result = await api.saveFeedback(episodeId, revision, { tags, note })
      setSaved(result)
      setTags(result.tags)
      setNote(result.note)
      setMessage('Feedback saved.')
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  const clear = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.clearFeedback(episodeId, revision)
      setSaved(null)
      setTags([])
      setNote('')
      setMessage('Feedback cleared.')
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
      setConfirmClear(false)
    }
  }

  return (
    <section className="card stack" aria-labelledby={`${id}-h`} data-testid="feedback-editor">
      <h2 id={`${id}-h`}>Feedback for the next batch</h2>
      <fieldset>
        <legend className="sublegend">Tags</legend>
        <div className="tag-chips">
          {FEEDBACK_TAGS.map((tag) => (
            <button
              key={tag}
              type="button"
              className="btn chip-toggle"
              aria-pressed={tags.includes(tag)}
              onClick={() => toggle(tag)}
              disabled={busy}
            >
              {TAG_LABELS[tag]}
            </button>
          ))}
        </div>
      </fieldset>
      <TextCounterField
        label="Note"
        value={note}
        onChange={(value) => {
          setMessage('')
          setNote(value)
        }}
        counter={noteCounter}
        hint="What to keep or change next time. May mention the answer; it is never published."
        rows={4}
      />
      <p className="muted" role="status" aria-live="polite">
        {message ? `${message} ` : ''}
        {dirty ? 'Unsaved changes.' : saved ? null : 'No feedback saved for this episode.'}
      </p>
      {saved && !dirty ? (
        <p className="muted">
          Saved <Time iso={saved.updatedAt} zone={zone} /> · {saved.status === 'used' ? 'used in a brief' : 'open (goes into the next brief)'}
        </p>
      ) : null}
      <div className="actions">
        <button type="button" className="btn btn-primary" onClick={() => void save()} disabled={!canSave}>
          {busy ? 'Saving…' : 'Save feedback'}
        </button>
        <button type="button" className="btn" onClick={() => setConfirmClear(true)} disabled={busy || !saved}>
          Clear
        </button>
      </div>
      <ErrorNotice error={error} title="Feedback not saved" />
      {confirmClear ? (
        <ConfirmDialog title="Clear this feedback?" confirmLabel="Clear feedback" danger busy={busy} onConfirm={() => void clear()} onCancel={() => setConfirmClear(false)}>
          <p>The tags and note for this episode are removed from the Pi.</p>
        </ConfirmDialog>
      ) : null}
    </section>
  )
}
