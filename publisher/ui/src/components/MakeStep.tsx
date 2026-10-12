import { useId, type ReactNode } from 'react'

/** One numbered step of Studio › Make a batch, saying where it happens. */
export function MakeStep({ n, title, where, children, testId }: { n: number; title: string; where: 'Pi' | 'Mac'; children: ReactNode; testId?: string }) {
  const id = useId()
  return (
    <section className="card stack" aria-labelledby={id} data-testid={testId}>
      <h2 id={id} className="make-step-title">
        <span className="loop-num" aria-hidden="true">
          {n}
        </span>
        {title}
        <span className={`where where-${where.toLowerCase()}`}>{where === 'Mac' ? 'on the Mac' : 'here on the Pi'}</span>
      </h2>
      {children}
    </section>
  )
}
