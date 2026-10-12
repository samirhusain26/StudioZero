import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import type { LibraryResponse } from '../../api/types'
import { ActionBar } from '../../components/ActionBar'
import { Chip } from '../../components/Chip'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Loading } from '../../components/Loading'
import { ScreenHelp } from '../../components/ScreenHelp'
import { StatusBadge } from '../../components/StatusBadge'
import { useApi } from '../../hooks/useApi'
import { dragHasFiles, entriesFromDataTransfer } from '../../lib/dropFolder'
import {
  approvableShown,
  batchChips,
  filterCounts,
  LIBRARY_FILTERS,
  listEpisodes,
  readListState,
  writeListState,
  type LibraryListState,
} from '../../lib/libraryList'
import { AddBatchFlow, type DroppedFolder } from './AddBatchFlow'
import { useContentActions } from './ContentActions'
import { EpisodeCard } from './EpisodeCard'
import { RemovePostedVideos } from './RemovePostedVideos'

/** Library list (Upload and Review): drop zone, batch chips, To review / Approved / All, tap a card to review it. */
export function LibraryView() {
  const { data, error, loading, reload } = useApi(api.library)
  const [dragging, setDragging] = useState(false)
  const [dropped, setDropped] = useState<DroppedFolder | null>(null)
  const [dropError, setDropError] = useState<string | null>(null)

  // Drop the batch folder anywhere on the Library page: the entries must be taken during the drop event.
  useEffect(() => {
    let depth = 0
    const enter = (e: DragEvent) => {
      if (!dragHasFiles(e.dataTransfer)) return
      depth++
      setDragging(true)
    }
    const leave = (e: DragEvent) => {
      if (!dragHasFiles(e.dataTransfer)) return
      depth = Math.max(0, depth - 1)
      if (depth === 0) setDragging(false)
    }
    const over = (e: DragEvent) => {
      if (!dragHasFiles(e.dataTransfer)) return
      e.preventDefault()
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
    }
    const drop = (e: DragEvent) => {
      if (!dragHasFiles(e.dataTransfer)) return
      e.preventDefault()
      depth = 0
      setDragging(false)
      const entries = entriesFromDataTransfer(e.dataTransfer)
      if (!entries) {
        setDropError('This browser cannot read a dropped folder. Use “Batch folder” to choose it instead.')
        return
      }
      setDropError(null)
      setDropped({ entries, nonce: Date.now() })
    }
    window.addEventListener('dragenter', enter)
    window.addEventListener('dragleave', leave)
    window.addEventListener('dragover', over)
    window.addEventListener('drop', drop)
    return () => {
      window.removeEventListener('dragenter', enter)
      window.removeEventListener('dragleave', leave)
      window.removeEventListener('dragover', over)
      window.removeEventListener('drop', drop)
    }
  }, [])

  const toReview = data ? data.episodes.filter((e) => e.status === 'reviewable' || e.status === 'withdrawn').length : 0
  return (
    <div className="stack-lg">
      {dragging ? (
        <div className="drop-overlay" aria-hidden="true">
          <p>Drop the batch folder to add it</p>
        </div>
      ) : null}
      <ScreenHelp id="library" />
      <div className="actions">
        {/* Primary only when there is nothing to review: then making the next batch is the way forward. */}
        <a className={`btn${data && toReview === 0 ? ' btn-primary' : ''}`} href="#/studio/make">
          + Make a batch
        </a>
      </div>
      {dropError ? (
        <p className="notice notice-error" role="alert">
          {dropError}
        </p>
      ) : null}
      <AddBatchFlow dropped={dropped} onDone={reload} />
      <ErrorNotice error={error} title="Library unavailable" />
      {data ? <LibraryBrowser data={data} onChanged={reload} /> : loading ? <Loading /> : null}
      {data ? (
        <details className="disclosure">
          <summary>Free space on the Pi</summary>
          <RemovePostedVideos onChanged={reload} />
        </details>
      ) : null}
    </div>
  )
}

export function LibraryBrowser({ data, onChanged }: { data: LibraryResponse; onChanged: () => void }) {
  const [state, setStateRaw] = useState<LibraryListState>(() => {
    const saved = readListState()
    return data.batches.some((b) => b.batchId === saved.batchId) ? saved : { ...saved, batchId: '' }
  })
  const setState = (next: LibraryListState) => {
    setStateRaw(next)
    writeListState(next)
  }
  const shown = useMemo(() => listEpisodes(data, state), [data, state])
  const counts = filterCounts(data, state.batchId)
  const approvable = approvableShown(shown)
  const actions = useContentActions(onChanged)
  const batch = data.batches.find((b) => b.batchId === state.batchId)

  return (
    <section className="stack" aria-labelledby="episodes-h">
      <h2 id="episodes-h">Episodes</h2>
      {data.batches.length ? (
        <div className="chip-row scroll" role="group" aria-label="Batch">
          <Chip pressed={state.batchId === ''} onClick={() => setState({ ...state, batchId: '' })}>
            All batches · {data.episodes.length}
          </Chip>
          {batchChips(data).map((b) => (
            <Chip key={b.batchId} pressed={state.batchId === b.batchId} onClick={() => setState({ ...state, batchId: b.batchId })}>
              {b.label} · {b.count}
            </Chip>
          ))}
        </div>
      ) : null}
      <div className="chip-row" role="group" aria-label="Show">
        {LIBRARY_FILTERS.map((f) => (
          <Chip key={f.id} pressed={state.filter === f.id} onClick={() => setState({ ...state, filter: f.id })}>
            {f.label}
            {f.id === 'review' && counts.review ? (
              <>
                {' '}
                <span className="chip-count">● {counts.review}</span>
              </>
            ) : null}
          </Chip>
        ))}
      </div>
      {batch && (batch.awaitingFiles || batch.warnings.length || batch.generatorDirty) ? (
        <div className="notice notice-warn">
          {batch.awaitingFiles ? <p>{batch.awaitingFiles} episode(s) of this batch still need files: drop the folder again.</p> : null}
          {batch.generatorDirty ? <StatusBadge tone="warn" label="Generator had uncommitted changes" /> : null}
          {batch.warnings.map((w, i) => (
            <p key={`${w.path}-${i}`}>Warning: {w.message}</p>
          ))}
        </div>
      ) : null}
      {actions.status}
      {data.episodes.length === 0 ? (
        <p>
          Nothing to review yet. <a href="#/studio/make">Make a batch →</a>
        </p>
      ) : shown.length === 0 ? (
        state.filter === 'review' ? (
          <p>
            Nothing to review{state.batchId ? ' in this batch' : ''}.{' '}
            {counts.approved ? `${counts.approved} approved: they are ready for the Schedule. ` : ''}
            <a href="#/studio/make">Make a batch →</a>
          </p>
        ) : (
          <p>Nothing here. Pick another chip above.</p>
        )
      ) : (
        <div className="episode-grid">
          {shown.map((e) => (
            <EpisodeCard key={`${e.episodeId}@${e.revision}`} episode={e} />
          ))}
        </div>
      )}
      {state.filter === 'review' && shown.length >= 2 ? (
        <ActionBar label="Library actions">
          <button type="button" className="btn btn-primary" disabled={approvable.length === 0} onClick={() => actions.ask('approve', approvable)}>
            Approve all shown ({approvable.length})
          </button>
        </ActionBar>
      ) : null}
      {actions.dialog}
    </section>
  )
}
