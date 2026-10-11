import { formatClock } from '../lib/time'

/** "Updated 22:10:56 EDT · ↻ ⏸" — the one-line auto-refresh status under the title (Home and Activity only). */
export function RefreshLine({
  updatedAt,
  zone,
  auto,
  onToggle,
  onRefresh,
  loading,
  stopped,
}: {
  updatedAt: Date | null
  zone: string
  auto: boolean
  onToggle: (on: boolean) => void
  onRefresh: () => void
  loading: boolean
  stopped: string | null
}) {
  return (
    <div className="refresh-line">
      <p className="muted refresh-status" role="status" aria-live="polite">
        {updatedAt ? `Updated ${formatClock(updatedAt, zone)}` : 'Not loaded yet'}
        {stopped ? '' : auto ? '' : ' · auto-refresh paused'}
      </p>
      <button type="button" className="btn btn-icon" onClick={onRefresh} disabled={loading} aria-label={loading ? 'Refreshing' : 'Refresh now'} title="Refresh now">
        <span aria-hidden="true">↻</span>
      </button>
      <button
        type="button"
        className="btn btn-icon"
        onClick={() => onToggle(!auto)}
        aria-label={auto ? 'Pause auto-refresh' : 'Resume auto-refresh'}
        title={auto ? 'Pause auto-refresh (every 30 s while this tab is open)' : 'Resume auto-refresh'}
      >
        <span aria-hidden="true">{auto ? '⏸︎' : '▶︎'}</span>
      </button>
      {stopped ? (
        <p className="notice notice-warn refresh-stopped" role="alert">
          {stopped}
        </p>
      ) : null}
    </div>
  )
}
