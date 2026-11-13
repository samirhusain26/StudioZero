import { useEffect, useState } from 'react'
import { creationApi, type Production } from '../../api/creation'

export function CreationReviewQueue() {
  const [items, setItems] = useState<Production[]>([])
  const [error, setError] = useState('')
  useEffect(() => { void creationApi.list().then(({ productions }) => setItems(productions.filter((p) => p.currentRevisionId && p.project !== 'originals'))).catch(() => setError('Cuts could not be loaded. Reload to try again.')) }, [])
  const cuts = items.filter((p) => p.revisions.find((r) => r.id === p.currentRevisionId)?.cutApproval == null)
  return <section className="card stack" aria-labelledby="creation-review-heading"><h2 id="creation-review-heading">Cuts to review <span className="muted">· {cuts.length} productions</span></h2>
    {error ? <p role="alert">{error}</p> : cuts.length ? <ul>{cuts.map((p) => <li key={p.id}><a href={`#/studio/create?project=${encodeURIComponent(p.project)}&production=${encodeURIComponent(p.id)}`}>{p.title || p.brief.slice(0, 90)}</a> · {p.project}{p.project === 'explainers' && p.research.status !== 'accepted' ? ' · research held' : ''}</li>)}</ul> : <p className="muted">No unfinished cuts need a decision.</p>}
  </section>
}
