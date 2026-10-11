import type { ApprovalResult } from '../api/types'
import { shortHash } from './format'
import type { Tone } from './labels'

export function approvalResultText(result: ApprovalResult): { tone: Tone; label: string; detail: string } {
  switch (result.status) {
    case 'manifest-ready':
      return {
        tone: 'info',
        label: 'Manifest ready',
        detail: `Manifest ${shortHash(result.manifestSha256)} with ${result.jobs} jobs; ${result.deployment.verified} of ${result.deployment.files} media files verified. Waiting for the bind step.`,
      }
    case 'bound':
      return {
        tone: 'good',
        label: 'Bound',
        detail: `Manifest ${shortHash(result.manifestSha256)} (${result.jobs} jobs) is the approved schedule.`,
      }
    case 'validated-no-deploy':
      return {
        tone: 'info',
        label: 'Validated (staging, not deployed)',
        detail: 'Staging mode: nothing was deployed and no config changed.',
      }
    case 'failed':
      return { tone: 'bad', label: 'Failed', detail: result.message }
  }
}
