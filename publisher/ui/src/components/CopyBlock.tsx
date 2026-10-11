import { useState } from 'react'

export function CopyBlock({ code, label }: { code: string; label: string }) {
  const [status, setStatus] = useState('')
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setStatus('Copied to the clipboard.')
    } catch {
      setStatus('Copy failed; select the text and copy it manually.')
    }
  }
  return (
    <figure className="copy-block">
      <figcaption>{label}</figcaption>
      <pre>
        <code>{code}</code>
      </pre>
      <div className="actions">
        <button type="button" className="btn" onClick={copy}>
          Copy command
        </button>
        <span role="status" aria-live="polite" className="muted">
          {status}
        </span>
      </div>
    </figure>
  )
}
