import type { Tone } from '../lib/labels'

/** Text label first; colour is a secondary cue only. */
export function StatusBadge({ tone, label, className }: { tone: Tone; label: string; className?: string }) {
  return (
    <span className={`badge badge-${tone}${className ? ` ${className}` : ''}`}>
      <span className="badge-mark" aria-hidden="true">
        {tone === 'good' ? '✓' : tone === 'bad' ? '✕' : tone === 'warn' ? '!' : '•'}
      </span>
      {label}
    </span>
  )
}
