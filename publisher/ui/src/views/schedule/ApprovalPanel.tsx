import { useId } from 'react'
import type { ApprovalRequestState, ApprovalResult, DraftResponse } from '../../api/types'
import { ErrorNotice } from '../../components/ErrorNotice'
import { ScreenHelp } from '../../components/ScreenHelp'
import { StatusBadge } from '../../components/StatusBadge'
import { Time } from '../../components/Time'
import { approvalGate, confirmationPhrase } from '../../lib/confirm'
import { shortHash } from '../../lib/format'
import { approvalResultText } from '../../lib/approvalResult'

export function ApprovalPanel({
  draft,
  pendingRequest,
  lastResult,
  zone,
  busy,
  error,
  onApprove,
}: {
  draft: DraftResponse
  pendingRequest: ApprovalRequestState | null
  /** Last result for this draft only. */
  lastResult: ApprovalResult | null
  zone: string
  busy: boolean
  error: unknown
  onApprove: (confirmation: string) => void
}) {
  const id = useId()
  const phrase = draft.confirmationPhrase || confirmationPhrase(draft.sha256)
  const pendingThis = pendingRequest?.draftSha256 === draft.sha256
  const gate = approvalGate({ blockingProblems: draft.blockingProblems, pending: pendingRequest !== null })
  return (
    <section className="card stack" aria-labelledby={`${id}-h`} data-testid="approval-panel">
      <h2 id={`${id}-h`}>Approve this draft</h2>
      <ScreenHelp id="approval" />
      <p>Approving deploys and checks the media, then publishing starts automatically.</p>
      <p id={`${id}-gate`} className="hint" aria-live="polite">
        {gate.allowed ? 'Ready to approve.' : gate.reason}
      </p>
      <div className="actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={!gate.allowed || busy}
          aria-describedby={`${id}-gate`}
          onClick={() => onApprove(phrase)}
        >
          {busy ? 'Requesting…' : 'Approve schedule'}
        </button>
      </div>
      <div role="status" aria-live="polite" className="stack">
        {pendingThis && pendingRequest ? (
          <p className="notice notice-info">
            <StatusBadge tone="info" label="Request pending" /> Requested <Time iso={pendingRequest.requestedAt} zone={zone} />. The applier
            deploys and verifies media; this can take a few minutes.
          </p>
        ) : pendingRequest ? (
          <p className="notice notice-warn">
            Another approval (draft <code>{shortHash(pendingRequest.draftSha256)}</code>) is pending. Wait for its result.
          </p>
        ) : null}
        {lastResult ? (
          <p className={`notice ${lastResult.status === 'failed' ? 'notice-error' : 'notice-info'}`}>
            <StatusBadge {...badge(lastResult)} /> {approvalResultText(lastResult).detail}
          </p>
        ) : null}
      </div>
      <ErrorNotice error={error} title="Approval request failed" />
    </section>
  )
}

function badge(result: ApprovalResult) {
  const { tone, label } = approvalResultText(result)
  return { tone, label }
}
