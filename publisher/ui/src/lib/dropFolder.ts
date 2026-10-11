/**
 * Drag-and-drop of a batch folder: walk the dropped FileSystemEntry tree
 * (DataTransferItem.webkitGetAsEntry) into the same `{file, path}` list a folder picker gives
 * (path relative to the dropped folder's parent, like webkitRelativePath), so lib/batchFolder.ts
 * handles both the same way.
 */

export interface PathFile {
  file: File
  path: string
  size: number
}

/** The parts of FileSystemEntry / FileSystemDirectoryReader this walk uses (easy to fake in tests). */
export interface EntryLike {
  isFile: boolean
  isDirectory: boolean
  name: string
  fullPath: string
  file?: (success: (file: File) => void, error?: (err: unknown) => void) => void
  createReader?: () => { readEntries: (success: (entries: EntryLike[]) => void, error?: (err: unknown) => void) => void }
}

function readFile(entry: EntryLike): Promise<File> {
  return new Promise((resolve, reject) => {
    if (!entry.file) reject(new Error(`Cannot read ${entry.fullPath}`))
    else entry.file(resolve, reject)
  })
}

/** All children of a directory: readEntries returns batches (Chrome: 100) until an empty one. */
async function readAll(entry: EntryLike): Promise<EntryLike[]> {
  const reader = entry.createReader?.()
  if (!reader) return []
  const out: EntryLike[] = []
  for (;;) {
    const batch = await new Promise<EntryLike[]>((resolve, reject) => reader.readEntries(resolve, reject))
    if (batch.length === 0) return out
    out.push(...batch)
  }
}

function relativePath(entry: EntryLike): string {
  return (entry.fullPath || entry.name).replace(/^\/+/, '')
}

/** Walk dropped entries depth-first into path-tagged files (hidden files such as .DS_Store are kept; batchFolder ignores them). */
export async function filesFromEntries(entries: readonly EntryLike[]): Promise<PathFile[]> {
  const out: PathFile[] = []
  const walk = async (entry: EntryLike): Promise<void> => {
    if (entry.isFile) {
      const file = await readFile(entry)
      out.push({ file, path: relativePath(entry), size: file.size })
    } else if (entry.isDirectory) {
      for (const child of await readAll(entry)) await walk(child)
    }
  }
  for (const entry of entries) await walk(entry)
  return out
}

/**
 * Entries must be taken synchronously inside the drop handler (the DataTransfer is emptied after it
 * returns). Returns null when the browser cannot give folder entries (use the folder picker instead).
 */
export function entriesFromDataTransfer(dataTransfer: DataTransfer | null): EntryLike[] | null {
  if (!dataTransfer?.items || dataTransfer.items.length === 0) return null
  const entries: EntryLike[] = []
  for (const item of Array.from(dataTransfer.items)) {
    if (item.kind !== 'file' || typeof item.webkitGetAsEntry !== 'function') return null
    const entry = item.webkitGetAsEntry() as EntryLike | null
    if (entry) entries.push(entry)
  }
  return entries.length ? entries : null
}

/** Whether a drag carries files (so the page can show the drop target). */
export function dragHasFiles(dataTransfer: DataTransfer | null): boolean {
  return Boolean(dataTransfer && Array.from(dataTransfer.types ?? []).includes('Files'))
}
