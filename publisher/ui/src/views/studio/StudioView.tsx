import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import { creationApi, type Production } from '../../api/creation'
import type { LibraryResponse } from '../../api/types'

const PROJECTS = [
  { id: 'scalargame', name: 'Scalargame', summary: 'Visual quizzes.', state: 'Create here or hand off a research task.' },
  { id: 'explainers', name: 'Explainers', summary: 'Ideas, explained.', state: 'Research decision before a cut · local delivery.' },
  { id: 'marathon', name: 'Marathon', summary: 'Your weekly story.', state: 'Manual delivery · private inputs stay local.' },
  { id: 'originals', name: 'Originals', summary: 'Recaps and series.', state: 'On hold · paid work needs owner approval.' },
]

export function StudioView() {
  const [library, setLibrary] = useState<LibraryResponse | null>(null)
  const [productions, setProductions] = useState<Production[]>([])
  const [errors, setErrors] = useState<string[]>([])
  useEffect(() => {
    void api.library().then(setLibrary).catch(() => setErrors((x) => [...x, 'Existing publishing batches could not be loaded.']))
    void creationApi.list().then((x) => setProductions(x.productions)).catch(() => setErrors((x) => [...x, 'Saved local productions could not be loaded.']))
  }, [])
  return <div className="studio-home">
    <p className="muted">Choose a project to start or resume a production.</p>
    <div className="project-grid">
      {PROJECTS.map((project) => {
        const saved = productions.filter((p) => p.project === project.id).length
        const batches = library?.batches.filter((batch) => library.episodes.some((episode) => episode.batchId === batch.batchId && episode.project === project.id)).length ?? 0
        return <section className="card project-card" key={project.id} aria-labelledby={`project-${project.id}`}>
          <span className="project-mark">{project.id === 'originals' ? 'On hold' : project.id === 'marathon' ? 'Manual' : project.id === 'explainers' ? 'Local delivery' : 'Studio project'}</span>
          <h2 id={`project-${project.id}`}>{project.name}</h2><p>{project.summary}</p><p className="muted">{project.state} {saved ? `· ${saved} saved productions` : ''} {batches ? `· ${batches} batches` : ''}</p>
          <a className="btn" aria-label={`Open ${project.name}`} href={`#/studio/project/${project.id}`}>Open <span aria-hidden="true">→</span></a>
        </section>
      })}
    </div>
    <details><summary>More tools</summary><nav aria-label="More Studio tools" className="studio-tools"><a href="#/studio/export">Scalargame browser preview and export</a><a href="#/studio/jobs">Story worker jobs</a><a href="#/studio/new">Legacy format tools</a></nav></details>
    {errors.map((error) => <p className="notice notice-warn" role="status" key={error}>{error}</p>)}
  </div>
}
