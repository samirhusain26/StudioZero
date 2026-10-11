/** Schedule approval phrase `APPROVE <first 8 hex>`: the Approve button sends it; the owner types nothing. */
export function confirmationPhrase(sha256: string): string {
  return `APPROVE ${sha256.slice(0, 8)}`
}

export interface ApprovalGate {
  allowed: boolean
  reason: string | null
}

/** Approve is enabled unless something blocks it or another approval is pending. */
export function approvalGate(options: { blockingProblems: readonly string[]; pending: boolean }): ApprovalGate {
  if (options.blockingProblems.length > 0) return { allowed: false, reason: 'Blocking problems must be resolved first.' }
  if (options.pending) return { allowed: false, reason: 'An approval request is already pending.' }
  return { allowed: true, reason: null }
}
