import { useState } from 'react'
import { api } from '../../api/client'
import { ErrorNotice } from '../../components/ErrorNotice'
import { ConfirmDialog } from '../../components/Modal'
import { StatusBadge } from '../../components/StatusBadge'

export function PublishingControl({ paused, onPaused }: { paused: boolean; onPaused: () => void }) {
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [error, setError] = useState<unknown>(null)
  const pause = async () => {
    setBusy(true)
    setError(null)
    try {
      const response = await api.pause()
      setResult(response.alreadyPaused ? 'Publishing was already paused.' : 'Publishing paused. The publisher stops before its next job.')
      onPaused()
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
      setConfirming(false)
    }
  }
  return (
    <section className="card" aria-labelledby="pause-h">
      <h2 id="pause-h">Publishing control</h2>
      <p>
        Publishing is <StatusBadge tone={paused ? 'neutral' : 'warn'} label={paused ? 'Paused' : 'Not paused'} />
      </p>
      <div className="actions">
        <button type="button" className="btn btn-danger" onClick={() => setConfirming(true)}>
          Pause publishing
        </button>
      </div>
      <p className="hint">
        The autopilot schedules and publishes approved library videos by itself. Pausing stops the publisher and the autopilot; resuming is
        not possible from this UI, it is an owner sudo command on the Pi —{' '}
        <a href="#/settings#activation">see Activation</a>
        .
      </p>
      <div aria-live="polite" role="status">
        {result ? <p className="notice notice-info">{result}</p> : null}
      </div>
      <ErrorNotice error={error} title="Pause failed" />
      {confirming ? (
        <ConfirmDialog
          title="Pause publishing?"
          confirmLabel="Pause now"
          danger
          busy={busy}
          onConfirm={pause}
          onCancel={() => setConfirming(false)}
        >
          <p>This writes the PAUSED sentinel. The publisher checks it between jobs and stops sending.</p>
          <p>Jobs already sent stay as they are. The autopilot schedules nothing while paused. Resuming needs the owner sudo command.</p>
        </ConfirmDialog>
      ) : null}
    </section>
  )
}
