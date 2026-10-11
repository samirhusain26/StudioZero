import type { ReactNode } from 'react'

/** Sticky action row: pinned above the tab bar on phones, inline on desktop. Holds a screen's main buttons. */
export function ActionBar({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="action-bar" role="group" aria-label={label} data-testid="action-bar">
      {children}
    </div>
  )
}
