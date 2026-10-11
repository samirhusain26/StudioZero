import type { StepState } from '../lib/journey'

const STATE_WORDS: Record<StepState, string | null> = { current: 'your next step', blocked: 'blocked', done: 'done', todo: null }

/** "Step 3 of 6 · Review" under each screen title: orientation within the loop (the tab bar is for jumping). */
export function StepLine({ step }: { step: { n: number; label: string; state: StepState | null } | null }) {
  if (!step) return null
  const word = step.state ? STATE_WORDS[step.state] : null
  return (
    <p className={`step-line${step.state ? ` step-line-${step.state}` : ''}`} data-testid="step-line">
      Step {step.n} of 6 · {step.label}
      {word ? <span className="step-line-state"> · {word}</span> : null}
    </p>
  )
}
