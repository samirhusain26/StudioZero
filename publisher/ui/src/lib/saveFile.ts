/** Save text generated in the page as a file (no network). */
export function saveTextFile(name: string, text: string, type = 'application/json'): void {
  saveBlob(name, new Blob([text], { type }))
}

/** Save a file made in the page (e.g. an exported MP4) to the device (no network). */
export function saveBlob(name: string, blob: Blob): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.rel = 'noopener'
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 30_000)
}

/** Copy to the clipboard; resolves false when the browser refuses (the caller shows the text to copy by hand). */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}
