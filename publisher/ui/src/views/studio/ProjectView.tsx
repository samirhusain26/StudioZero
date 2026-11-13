import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { creationApi, type Production } from '../../api/creation'
import type { LibraryResponse } from '../../api/types'

const NAMES: Record<string, string> = { scalargame: 'Scalargame', explainers: 'Explainers', marathon: 'Marathon', originals: 'Originals' }

export function ProjectView({ project }: { project?: string | undefined }) {
  const [library, setLibrary] = useState<LibraryResponse | null>(null)
  const [productions, setProductions] = useState<Production[]>([])
  const [error, setError] = useState('')
  useEffect(() => {
    let live = true
    void Promise.all([api.library(), creationApi.list()]).then(([l, c]) => { if (!live) return; setLibrary(l); setProductions(c.productions.filter((p) => p.project === project)) })
      .catch((e: unknown) => { if (live) setError(e instanceof Error ? e.message : 'Could not load project work.') })
    return () => { live = false }
  }, [project])
  const batches = library?.batches.filter((batch) => library.episodes.some((episode) => episode.batchId === batch.batchId && episode.project === project)) ?? []
  const manual = project === 'marathon'
  const held = project === 'originals'
  const explainers = project === 'explainers'
  return <div className="creation-workspace">
    <p><a href="#/home">← Studio</a></p>
    <h2>{NAMES[project ?? ''] ?? 'Project'}</h2>
    {project === 'scalargame' ? <p>Visual quizzes · create here, use the browser preview, or hand off unsupported work.</p> : null}
    {explainers ? <p>Choose an owner supplied topic. Research has to support the angle before a cut can be returned. Delivery stays local.</p> : null}
    {manual ? <p>Private weekly story. Keep raw health inputs and footage local; the owner posts manually.</p> : null}
    {held ? <p className="notice notice-warn">Originals is on hold. No generation starts here; each paid run needs explicit owner authorization and a cost estimate.</p> : null}
    <section className="card stack"><h3>Your videos</h3>
      {productions.length ? <ul>{productions.map((p) => <li key={p.id}><a href={`#/studio/create?project=${encodeURIComponent(project ?? '')}&production=${encodeURIComponent(p.id)}`}>{p.title || p.brief.slice(0, 80)}</a> · {p.currentRevisionId ? (p.revisions.find((r) => r.id === p.currentRevisionId)?.cutApproval ? 'cut approved' : 'cut to review') : p.project === 'originals' ? 'on hold' : p.project === 'explainers' && p.research.status !== 'accepted' ? (p.research.status === 'held' ? 'topic held' : 'research needed') : 'waiting for files'}</li>)}</ul> : <p className="muted">No saved productions yet.</p>}
      {batches.length ? <><h3>Existing batches</h3><ul>{batches.map((b) => <li key={b.batchId}><a href={`#/library?project=${encodeURIComponent(project ?? "")}&batch=${encodeURIComponent(b.batchId)}`}>{b.batchId}</a> · {b.episodeCount} videos</li>)}</ul></> : null}
      {held ? null : <a className="btn btn-primary" href={`#/studio/create?project=${encodeURIComponent(project ?? '')}`}>{manual ? 'Start this week’s story' : explainers ? 'Explain a topic' : 'Start a brief'}</a>}
    </section>
    {project === 'scalargame' ? <nav className="studio-tools" aria-label="Scalargame tools"><a href="#/studio/export">Preview and export in browser</a><a href="#/studio/make?project=scalargame">Legacy batch workflow</a></nav> : null}
    {manual ? <a href="#/guide/marathon">Open the Marathon guide</a> : null}
    {error ? <p className="notice notice-warn" role="status">{error}</p> : null}
  </div>
}
