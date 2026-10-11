/** Spoiler toggle: content it controls is not rendered at all until revealed. */
export function RevealToggle({
  revealed,
  onToggle,
  controls,
  showLabel = 'Reveal answer',
  hideLabel = 'Hide answer',
}: {
  revealed: boolean
  onToggle: (next: boolean) => void
  controls: string
  showLabel?: string
  hideLabel?: string
}) {
  return (
    <button type="button" className="btn reveal-toggle" aria-expanded={revealed} aria-controls={controls} onClick={() => onToggle(!revealed)}>
      {revealed ? hideLabel : showLabel}
    </button>
  )
}
