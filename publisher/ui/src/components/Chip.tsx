import type { ReactNode } from 'react'

/** A filter chip: a toggle button (`aria-pressed`), used in a `role="group"` row instead of a select. */
export function Chip({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button type="button" className="chip-btn" aria-pressed={pressed} onClick={onClick}>
      {children}
    </button>
  )
}
