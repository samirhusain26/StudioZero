import { useId } from 'react'
import type { CounterState } from '../lib/contract'

/** Labelled textarea/input with a live character counter and inline issues. */
export function TextCounterField({
  label,
  value,
  onChange,
  counter,
  issues = [],
  hint,
  multiline = true,
  required = false,
  rows = 3,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  counter: CounterState
  issues?: string[]
  hint?: string
  multiline?: boolean
  required?: boolean
  rows?: number
}) {
  const id = useId()
  const counterId = `${id}-count`
  const hintId = `${id}-hint`
  const describedBy = [counterId, hint ? hintId : null, issues.length ? `${id}-issues` : null].filter(Boolean).join(' ')
  return (
    <div className="field">
      <label htmlFor={id}>
        {label}
        {required ? <span className="req"> (required)</span> : null}
      </label>
      {hint ? (
        <p id={hintId} className="hint">
          {hint}
        </p>
      ) : null}
      {multiline ? (
        <textarea
          id={id}
          rows={rows}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-describedby={describedBy}
          aria-invalid={counter.over || issues.length > 0}
        />
      ) : (
        <input
          id={id}
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-describedby={describedBy}
          aria-invalid={counter.over || issues.length > 0}
        />
      )}
      <p id={counterId} className={`counter${counter.over ? ' counter-over' : ''}`} aria-live="polite">
        {counter.over ? 'Too long: ' : 'Characters: '}
        {counter.label}
      </p>
      {issues.length ? (
        <ul id={`${id}-issues`} className="field-issues">
          {issues.map((issue) => (
            <li key={issue}>{issue}</li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
