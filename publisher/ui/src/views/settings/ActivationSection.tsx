import { api } from '../../api/client'
import { CopyBlock } from '../../components/CopyBlock'
import { ErrorNotice } from '../../components/ErrorNotice'
import { Loading } from '../../components/Loading'
import { ScreenHelp } from '../../components/ScreenHelp'
import { StatusBadge } from '../../components/StatusBadge'
import { useApi } from '../../hooks/useApi'
import { platformName, shortHash } from '../../lib/format'

/** Removing the UI's pause sentinel; the publisher resumes on its next tick and the autopilot on its next run. */
const RESUME_COMMAND = 'sudo rm /var/lib/scalar-social/PAUSED'

/** Settings › Activation: the readiness checklist the autopilot runs, and the owner's commands (shown for copying; nothing runs here). */
export function ActivationSection() {
  const { data, error, loading, reload } = useApi(api.activation)
  return (
    <section className="card stack" aria-labelledby="activation-h">
      <h2 id="activation-h">Activation</h2>
      <ScreenHelp id="activation" />
      <section className="notice notice-info" aria-labelledby="act-l3">
        <h3 id="act-l3" className="h4">
          This UI cannot resume publishing
        </h3>
        <p>
          After the owner’s one-time first activation, the autopilot enables exactly the approved channels and keeps the publisher timer on
          by itself. It never resumes a pause from Settings: to resume, the owner runs the Resume command below with sudo on the Pi, and the
          autopilot picks up again on its next run.
        </p>
      </section>
      <div className="toolbar">
        <button type="button" className="btn" onClick={reload} disabled={loading}>
          {loading ? 'Refreshing…' : 'Re-check'}
        </button>
      </div>
      <ErrorNotice error={error} title="Readiness unavailable" />
      {loading && !data ? <Loading /> : null}
      {data ? (
        <>
          <section className="stack" aria-labelledby="check-h">
            <h3 id="check-h">Readiness checklist</h3>
            <p>
              Overall: <StatusBadge tone={data.ready ? 'good' : 'bad'} label={data.ready ? 'READY' : 'NOT READY'} />
            </p>
            <p>{data.explanation}</p>
            <p className="muted">
              Manifest {data.manifestSha256 ? <code>{shortHash(data.manifestSha256, 12)}</code> : 'none'} · scope{' '}
              {data.scope.length ? data.scope.map(platformName).join(', ') : 'none'}
            </p>
            <ul className="checklist">
              {data.items.map((item) => (
                <li key={item.id} className="check-item">
                  <StatusBadge tone={item.pass ? 'good' : 'bad'} label={item.pass ? 'PASS' : 'FAIL'} /> <strong>{item.label}</strong>
                  {item.detail ? <span className="block">{item.detail}</span> : null}
                  {!item.pass && item.nextAction ? <span className="block">Next step: {item.nextAction}</span> : null}
                </li>
              ))}
            </ul>
          </section>
          <section className="stack" aria-labelledby="cmd-h">
            <h3 id="cmd-h">Owner commands, on the Pi</h3>
            <CopyBlock label="Check only (changes nothing)" code={data.checkCommand} />
            <CopyBlock label="Resume after a pause (owner, sudo)" code={RESUME_COMMAND} />
            <CopyBlock label="First activation (owner, sudo; done once on 2026-10-09)" code={data.command} />
            <p className="hint">Displayed for copying only. Nothing on this page runs a command.</p>
          </section>
        </>
      ) : null}
    </section>
  )
}
