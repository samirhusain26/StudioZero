import { useEffect, useState, type FormEvent } from 'react'
import { api, ApiRequestError, clearPasscode, setPasscode, waitText } from '../api/client'
import type { HealthResponse } from '../api/types'
import { ErrorNotice } from '../components/ErrorNotice'

export function PasscodeView({ onSignedIn, notice }: { onSignedIn: () => void; notice: string | null }) {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [healthError, setHealthError] = useState<unknown>(null)
  const [passcode, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [lockedUntil, setLockedUntil] = useState<number | null>(null)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    let cancelled = false
    api.health().then(
      (h) => {
        if (cancelled) return
        setHealth(h)
        if (h.backoff.locked && h.backoff.retryAfterSeconds) setLockedUntil(Date.now() + h.backoff.retryAfterSeconds * 1000)
      },
      (e: unknown) => {
        if (!cancelled) setHealthError(e)
      },
    )
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (lockedUntil === null) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [lockedUntil])

  const remaining = lockedUntil === null ? 0 : Math.max(0, Math.ceil((lockedUntil - now) / 1000))
  const locked = remaining > 0

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!passcode || locked) return
    setBusy(true)
    setError(null)
    setPasscode(passcode)
    try {
      await api.loginSession(passcode)
      clearPasscode()
      setValue('')
      onSignedIn()
    } catch (e) {
      clearPasscode()
      if (e instanceof ApiRequestError && e.status === 429 && e.retryAfterSeconds) {
        setLockedUntil(Date.now() + e.retryAfterSeconds * 1000)
        setNow(Date.now())
      }
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main id="main" className="main passcode">
      <h1>Scalar publishing</h1>
      <p className="muted">Private publishing controls on the Pi. Enter the passcode to continue.</p>
      {notice ? (
        <p className="notice notice-info" role="status">
          {notice}
        </p>
      ) : null}
      <section aria-labelledby="pi-status" className="card">
        <h2 id="pi-status">Pi status</h2>
        <div role="status" aria-live="polite">
          {health ? (
            <p>Backend reachable (version {health.version}).</p>
          ) : healthError ? (
            <ErrorNotice error={healthError} title="Pi not reachable" />
          ) : (
            <p>Checking the Pi…</p>
          )}
          {locked ? (
            <p className="notice notice-warn">
              Locked after repeated wrong passcodes. Wait {waitText(remaining)} before the next attempt.
            </p>
          ) : null}
        </div>
      </section>
      <form onSubmit={submit} className="card stack" aria-labelledby="sign-in">
        <h2 id="sign-in">Sign in</h2>
        <div className="field">
          <label htmlFor="passcode">Passcode</label>
          <input
            id="passcode"
            type="password"
            autoComplete="current-password"
            value={passcode}
            onChange={(e) => setValue(e.target.value)}
            required
          />
          <p className="hint">Used once to create a secure sign-in session; the passcode is cleared from this page.</p>
        </div>
        <button type="submit" className="btn btn-primary" disabled={busy || locked || !passcode}>
          {busy ? 'Checking…' : 'Sign in'}
        </button>
        <div aria-live="assertive">{error ? <ErrorNotice error={error} title="Sign-in failed" /> : null}</div>
      </form>
    </main>
  )
}
