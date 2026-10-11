/**
 * The one "Next step" suggestion: the current-step rule of the loop, which lives in `journey.ts`
 * (`currentFocus`, priorities documented there). Kept as a small adapter for callers that only need
 * a title, a detail and where to go.
 */
import type { Standing, UpdateInfo } from '../api/types'
import { currentFocus, type StepAction, type StepId } from './journey'
import type { MakeProgress } from './makeChecklist'

export { RUNWAY_DAYS, STALE_BATCH_DAYS } from './journey'

export interface NextStep {
  step: StepId
  title: string
  detail: string
  /** Route path the step happens on (without `#/`), or null when nothing needs doing. */
  target: string | null
  action: StepAction | null
}

export function nextStep(args: {
  standing: Standing | null | undefined
  hasApprovedSchedule: boolean
  update: UpdateInfo | null
  now: Date
  paused?: boolean
  make?: MakeProgress | null
}): NextStep {
  const focus = currentFocus({ ...args, paused: args.paused ?? false, make: args.make ?? null })
  return { step: focus.step, title: focus.title, detail: focus.detail, target: focus.action?.to ?? null, action: focus.action }
}
