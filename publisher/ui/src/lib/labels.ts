import type { EpisodeStatus, HistoryStatus, IssueSeverity, LedgerStatus, TriState } from '../api/types'

export type Tone = 'good' | 'bad' | 'warn' | 'neutral' | 'info'

export function triTone(state: TriState): Tone {
  return state === 'yes' ? 'good' : state === 'no' ? 'bad' : 'warn'
}

export const EPISODE_STATUS: Record<EpisodeStatus, { label: string; tone: Tone }> = {
  awaiting_files: { label: 'Awaiting files', tone: 'warn' },
  reviewable: { label: 'Ready for review', tone: 'info' },
  approved: { label: 'Approved', tone: 'good' },
  withdrawn: { label: 'Withdrawn', tone: 'neutral' },
  expired: { label: 'Expired', tone: 'neutral' },
  invalid: { label: 'Invalid', tone: 'bad' },
}

export const LEDGER_STATUS: Record<HistoryStatus | 'not-enqueued', { label: string; tone: Tone }> = {
  'not-enqueued': { label: 'Not yet queued', tone: 'neutral' },
  ready: { label: 'Queued', tone: 'info' },
  dispatching: { label: 'Sending (unconfirmed)', tone: 'warn' },
  accepted: { label: 'Accepted, awaiting confirmation', tone: 'warn' },
  uncertain: { label: 'Uncertain — needs reconciliation', tone: 'warn' },
  confirmed: { label: 'Published', tone: 'good' },
  failed: { label: 'Failed', tone: 'bad' },
  expired: { label: 'Missed slot', tone: 'bad' },
  blocked: { label: 'Blocked', tone: 'bad' },
  cancelled: { label: 'Cancelled', tone: 'neutral' },
}

export function ledgerStatus(status: LedgerStatus | HistoryStatus | 'not-enqueued') {
  return LEDGER_STATUS[status]
}

export const SEVERITY: Record<IssueSeverity, { label: string; tone: Tone }> = {
  error: { label: 'Error', tone: 'bad' },
  warning: { label: 'Warning', tone: 'warn' },
  info: { label: 'Info', tone: 'info' },
}
