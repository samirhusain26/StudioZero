import { formatLocalAndUtc } from '../lib/time'

/** Local time (zone abbreviation from Intl) plus UTC. */
export function Time({ iso, zone }: { iso: string | null | undefined; zone: string }) {
  if (!iso) return <span className="muted">—</span>
  return <time dateTime={iso}>{formatLocalAndUtc(iso, zone)}</time>
}
