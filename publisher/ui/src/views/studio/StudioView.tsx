import { useMemo } from 'react'
import { api } from '../../api/client'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Loading } from '../../components/Loading'
import { ScreenHelp } from '../../components/ScreenHelp'
import { useApi } from '../../hooks/useApi'
import { computeRunway } from '../../lib/runway'
import { projectSummaries } from '../../lib/studio'
import { formatDayHeading } from '../../lib/time'

/** Studio › Overview: the Make step for every project (docs/STUDIO_PLAN.md §1 decisions 5 and 8). */
export function StudioView() {
  const catalog = useApi(api.catalog)
  // The approved queue gives each project's runway; a failure only hides it.
  const schedule = useApi(api.schedule)
  const runway = useMemo(() => (schedule.data ? computeRunway(schedule.data, null) : schedule.error ? null : undefined), [schedule.data, schedule.error])
  const projects = catalog.data ? projectSummaries(catalog.data, runway) : []
  return (
    <div className="stack-lg">
      <ScreenHelp id="studio" />
      <ErrorNotice error={catalog.error} title="Studio catalog unavailable" />
      {catalog.loading && !catalog.data ? <Loading /> : null}
      {projects.map((p) => (
        <section key={p.id} className="card stack" aria-labelledby={`studio-${p.id}`} data-testid="studio-project">
          <h2 id={`studio-${p.id}`}>
            {p.name} <span className="muted">· {p.priority}</span>
          </h2>
          <p>{p.summary}</p>
          <dl className="facts">
            <dt>Formats</dt>
            <dd>{p.formats.map((f) => f.name).join(', ')}</dd>
            <dt>Engine</dt>
            <dd>{p.engines.join(', ')}</dd>
            <dt>Budget</dt>
            <dd>{p.budget}</dd>
            <dt>Mix</dt>
            <dd>{p.mix}</dd>
            <dt>Runway</dt>
            <dd>
              {p.scheduledThrough === undefined
                ? 'Loading…'
                : p.scheduledThrough
                  ? `Scheduled through ${formatDayHeading(p.scheduledThrough)}`
                  : 'Nothing scheduled'}
            </dd>
          </dl>
          <div className="actions">
            <a className="btn" href={`#/studio/make?project=${encodeURIComponent(p.id)}`}>
              Make a {p.name} batch →
            </a>
          </div>
        </section>
      ))}
      {catalog.data ? (
        <section className="card stack" aria-labelledby="studio-engines">
          <h2 id="studio-engines">Engines</h2>
          <ul className="row-list">
            {catalog.data.engines.map((e) => (
              <li key={e.id} className="stack">
                <p className="row-head">
                  <strong>{e.name}</strong> <span className="muted">{e.kitVersion}</span>
                </p>
                <p>{e.summary}</p>
                <p className="muted">
                  {e.id === 'motion'
                    ? 'Runs in this browser: preview and export on the device you are using; nothing is rendered on the Pi.'
                    : 'Runs on the laptop worker; its jobs and spend appear here once the worker is set up.'}
                </p>
                {e.id === 'motion' ? (
                  <p>
                    <a href="#/studio/export">Preview and export a batch →</a>
                  </p>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}
