import { useId, useState, type ChangeEvent } from 'react'
import { api } from '../../api/client'
import type { BatchNote } from '../../api/types'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Loading } from '../../components/Loading'
import { Markdown } from '../../components/Markdown'
import { RevealToggle } from '../../components/RevealToggle'
import { Time } from '../../components/Time'
import { useApi } from '../../hooks/useApi'
import { utf8Bytes } from '../../lib/contract'
import { formatBytes } from '../../lib/format'

export const MAX_NOTE_BYTES = 65_536
type Kind = 'brief' | 'retro'
const FILE_NAME: Record<Kind, string> = { brief: 'BRIEF.md', retro: 'RETRO.md' }

/** Per-batch BRIEF.md / RETRO.md (may contain answers: shown only behind a toggle; never published). */
export function BatchNotesPanel({ batchId, zone }: { batchId: string; zone: string }) {
  const [open, setOpen] = useState(false)
  return (
    <details className="batch-notes" onToggle={(e) => setOpen(e.currentTarget.open)}>
      <summary>Notes (BRIEF.md / RETRO.md)</summary>
      {open ? <BatchNotesBody batchId={batchId} zone={zone} /> : null}
    </details>
  )
}

function NoteView({ note, kind, zone, revealed }: { note: BatchNote | null; kind: Kind; zone: string; revealed: boolean }) {
  return (
    <div className="stack">
      <p>
        <strong>{FILE_NAME[kind]}</strong>{' '}
        {note ? (
          <span className="muted">
            uploaded <Time iso={note.uploadedAt} zone={zone} /> · {formatBytes(note.bytes)}
          </span>
        ) : (
          <span className="muted">not uploaded yet</span>
        )}
      </p>
      {note && revealed ? <Markdown source={note.text} /> : null}
    </div>
  )
}

function BatchNotesBody({ batchId, zone }: { batchId: string; zone: string }) {
  const id = useId()
  const notes = useApi(() => api.batchNotes(batchId), batchId)
  const [revealed, setRevealed] = useState(false)
  const [kind, setKind] = useState<Kind>('brief')
  const [text, setText] = useState('')
  const [fileError, setFileError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [message, setMessage] = useState('')
  const bytes = utf8Bytes(text)
  const tooBig = bytes > MAX_NOTE_BYTES

  const chooseFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    setFileError(null)
    setMessage('')
    if (!file) return
    if (!/\.(md|markdown|txt)$/i.test(file.name)) {
      setFileError('Choose a .md or .txt file.')
      return
    }
    if (file.size > MAX_NOTE_BYTES) {
      setFileError(`${file.name} is ${formatBytes(file.size)}; the limit is 64 KiB.`)
      return
    }
    setText(await file.text())
    if (/retro/i.test(file.name)) setKind('retro')
    else if (/brief/i.test(file.name)) setKind('brief')
  }

  const save = async () => {
    setBusy(true)
    setError(null)
    setMessage('')
    try {
      const saved = await api.saveBatchNote(batchId, kind, text)
      if (notes.data) notes.setData({ ...notes.data, [kind]: saved })
      else notes.reload()
      setMessage(`${FILE_NAME[kind]} saved.`)
      setText('')
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      <ErrorNotice error={notes.error} title="Notes unavailable" />
      {notes.data ? (
        <>
          <div className="actions">
            <RevealToggle
              revealed={revealed}
              onToggle={setRevealed}
              controls={`${id}-notes`}
              showLabel="Show notes (may contain answers)"
              hideLabel="Hide notes"
            />
          </div>
          <div id={`${id}-notes`} className="stack">
            <NoteView note={notes.data.brief} kind="brief" zone={zone} revealed={revealed} />
            <NoteView note={notes.data.retro} kind="retro" zone={zone} revealed={revealed} />
          </div>
        </>
      ) : notes.loading ? (
        <Loading />
      ) : null}

      <fieldset className="stack">
        <legend className="sublegend">Add or replace a note</legend>
        <div className="segmented" role="group" aria-label="Which note">
          {(['brief', 'retro'] as const).map((k) => (
            <button key={k} type="button" className="btn" aria-pressed={kind === k} onClick={() => setKind(k)}>
              {FILE_NAME[k]}
            </button>
          ))}
        </div>
        <div className="field">
          <label htmlFor={`${id}-file`}>Choose a .md or .txt file</label>
          <input id={`${id}-file`} type="file" accept=".md,.markdown,.txt,text/markdown,text/plain" onChange={(e) => void chooseFile(e)} disabled={busy} />
        </div>
        {fileError ? (
          <p className="notice notice-error" role="alert">
            {fileError}
          </p>
        ) : null}
        <div className="field">
          <label htmlFor={`${id}-text`}>Or paste the text</label>
          <textarea id={`${id}-text`} rows={6} value={text} onChange={(e) => setText(e.target.value)} aria-describedby={`${id}-bytes`} aria-invalid={tooBig} />
          <p id={`${id}-bytes`} className={tooBig ? 'counter-over' : 'counter'} aria-live="polite">
            {tooBig ? 'Too long: ' : 'Size: '}
            {formatBytes(bytes)} of 64 KiB
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn btn-primary" onClick={() => void save()} disabled={busy || tooBig || text.trim() === ''}>
            {busy ? 'Saving…' : `Save ${FILE_NAME[kind]}`}
          </button>
        </div>
        <p role="status" aria-live="polite" className="muted">
          {message}
        </p>
        <ErrorNotice error={error} title="Note not saved" />
      </fieldset>
    </div>
  )
}
