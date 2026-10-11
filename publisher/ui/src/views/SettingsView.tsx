import { useState } from 'react'
import { api } from '../api/client'
import { ErrorNotice } from '../components/ErrorNotice'
import { Loading } from '../components/Loading'
import { useJourney } from '../hooks/useJourney'
import { ActivationSection } from './settings/ActivationSection'
import { PublishingControl } from './settings/PublishingControl'
import { SystemSection } from './settings/SystemSection'
import { UpdateSection } from './settings/UpdateSection'

/** Anchored sections of the one Settings page (`#/settings#<id>`), in page order. */
export const SETTINGS_SECTIONS = [
  { id: 'control', label: 'Publishing control' },
  { id: 'activation', label: 'Activation' },
  { id: 'update', label: 'Update' },
  { id: 'system', label: 'System' },
  { id: 'backup', label: 'Backup' },
  { id: 'session', label: 'Session' },
] as const

export function SettingsView({ onSignOut }: { onSignOut: () => void | Promise<void> }) {
  const { dashboard, reload } = useJourney()
  return (
    <div className="settings-layout">
      <nav className="settings-index" aria-label="On this page">
        <ul className="plain-list">
          {SETTINGS_SECTIONS.map((s) => (
            <li key={s.id}>
              <a href={`#/settings#${s.id}`}>{s.label}</a>
            </li>
          ))}
        </ul>
      </nav>
      <div className="stack-lg">
        <div id="control">{dashboard ? <PublishingControl paused={dashboard.paused} onPaused={reload} /> : <Loading />}</div>
        <div id="activation">
          <ActivationSection />
        </div>
        <div id="update">
          <UpdateSection />
        </div>
        <div id="system">{dashboard ? <SystemSection data={dashboard} /> : <Loading />}</div>
        <div id="backup">
          <BackupSection />
        </div>
        <div id="session">
          <SessionSection onSignOut={onSignOut} />
        </div>
      </div>
    </div>
  )
}

function BackupSection() {
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const backup = async () => {
    setBusy(true)
    setError(null)
    setStatus('Preparing the backup on the Pi…')
    try {
      const name = await api.backup()
      setStatus(`Downloaded ${name}.`)
    } catch (e) {
      setStatus('')
      setError(e)
    } finally {
      setBusy(false)
    }
  }
  return (
    <section className="card stack" aria-labelledby="backup-h">
      <h2 id="backup-h">Backup</h2>
      <p>
        Downloads a consistent ledger snapshot, the library index, manifests and batch.json files. It contains no media and no credentials.
        Store it somewhere other than the Pi.
      </p>
      <div className="actions">
        <button type="button" className="btn" onClick={backup} disabled={busy}>
          {busy ? 'Preparing…' : 'Download backup'}
        </button>
      </div>
      <p role="status" aria-live="polite">
        {status}
      </p>
      <ErrorNotice error={error} title="Backup failed" />
    </section>
  )
}

function SessionSection({ onSignOut }: { onSignOut: () => void | Promise<void> }) {
  const [signOutError, setSignOutError] = useState<string | null>(null)
  const [signingOut, setSigningOut] = useState(false)
  return (
    <section className="card stack" aria-labelledby="session-h">
      <h2 id="session-h">Session</h2>
      <p>Your browser has a private sign-in session (up to 90 days). Signing out revokes it. Changing the passcode on the Pi signs out every browser.</p>
      <div className="actions">
        <button type="button" className="btn" disabled={signingOut} onClick={() => {
          setSigningOut(true); setSignOutError(null)
          void Promise.resolve(onSignOut()).catch((reason: unknown) => setSignOutError(reason instanceof Error ? reason.message : 'The Pi could not be reached.')).finally(() => setSigningOut(false))
        }}>
          {signingOut ? 'Signing out…' : 'Sign out'}
        </button>
      </div>
      {signOutError ? <p className="notice notice-warn" role="alert">Could not sign out: {signOutError}. Try again.</p> : null}
    </section>
  )
}
