/**
 * Browser-local export progress (IndexedDB; an in-memory fallback when storage is blocked): the open job bundle and
 * every finished episode export (MP4, cover, measures), so a reload, a suspended tab or a crash resumes per episode.
 * Nothing here ever leaves the device except through the owner's upload.
 */
import type { DeliveryMeasures } from '../lib/media/deliveryQa'
import type { ExportedFiles } from './webPackage'

export interface StoredExport {
  batchId: string
  episodeId: string
  /** The job's propsHash when exported: a changed bundle makes the export stale. */
  propsHash: string
  mp4: Blob
  cover: Blob
  files: ExportedFiles
  measures: DeliveryMeasures
  errors: string[]
  master: { lufs: number; truePeakDbtp: number; ceilingDb: number }
  primingSamples: number
  seconds: number
  savedAt: string
}

export interface StoredBundle {
  batchId: string
  text: string
  savedAt: string
}

export interface MotionStore {
  getBundle(): Promise<StoredBundle | null>
  putBundle(bundle: StoredBundle): Promise<void>
  clear(batchId: string): Promise<void>
  getExports(batchId: string): Promise<StoredExport[]>
  putExport(item: StoredExport): Promise<void>
  /** Episodes that were exporting when the page went away. */
  markRunning(batchId: string, episodeId: string | null): Promise<void>
  running(batchId: string): Promise<string | null>
  /** True when progress survives a reload in this browser. */
  durable: boolean
}

export function memoryStore(): MotionStore {
  let bundle: StoredBundle | null = null
  const exports = new Map<string, StoredExport>()
  const running = new Map<string, string>()
  return {
    durable: false,
    getBundle: async () => bundle,
    putBundle: async (b) => {
      bundle = b
    },
    clear: async (batchId) => {
      if (bundle?.batchId === batchId) bundle = null
      for (const key of [...exports.keys()]) if (key.startsWith(`${batchId}/`)) exports.delete(key)
      running.delete(batchId)
    },
    getExports: async (batchId) => [...exports.values()].filter((e) => e.batchId === batchId),
    putExport: async (item) => {
      exports.set(`${item.batchId}/${item.episodeId}`, item)
    },
    markRunning: async (batchId, episodeId) => {
      if (episodeId) running.set(batchId, episodeId)
      else running.delete(batchId)
    },
    running: async (batchId) => running.get(batchId) ?? null,
  }
}

const DB = 'studio-motion'
const VERSION = 1

function request<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const open = indexedDB.open(DB, VERSION)
    open.onupgradeneeded = () => {
      const db = open.result
      if (!db.objectStoreNames.contains('meta')) db.createObjectStore('meta')
      if (!db.objectStoreNames.contains('exports')) db.createObjectStore('exports')
    }
    open.onsuccess = () => resolve(open.result)
    open.onerror = () => reject(open.error)
    open.onblocked = () => reject(new Error('IndexedDB is blocked by another tab.'))
  })
}

function idbStore(db: IDBDatabase): MotionStore {
  const tx = (names: string[], mode: IDBTransactionMode) => db.transaction(names, mode)
  return {
    durable: true,
    getBundle: async () => ((await request(tx(['meta'], 'readonly').objectStore('meta').get('bundle'))) as StoredBundle | undefined) ?? null,
    putBundle: async (bundle) => {
      await request(tx(['meta'], 'readwrite').objectStore('meta').put(bundle, 'bundle'))
    },
    clear: async (batchId) => {
      const t = tx(['meta', 'exports'], 'readwrite')
      const meta = t.objectStore('meta')
      const current = (await request(meta.get('bundle'))) as StoredBundle | undefined
      if (current?.batchId === batchId) await request(meta.delete('bundle'))
      await request(meta.delete(`running/${batchId}`))
      await request(t.objectStore('exports').delete(IDBKeyRange.bound(`${batchId}/`, `${batchId}/￿`)))
    },
    getExports: async (batchId) =>
      (await request(tx(['exports'], 'readonly').objectStore('exports').getAll(IDBKeyRange.bound(`${batchId}/`, `${batchId}/￿`)))) as StoredExport[],
    putExport: async (item) => {
      await request(tx(['exports'], 'readwrite').objectStore('exports').put(item, `${item.batchId}/${item.episodeId}`))
    },
    markRunning: async (batchId, episodeId) => {
      const meta = tx(['meta'], 'readwrite').objectStore('meta')
      if (episodeId) await request(meta.put(episodeId, `running/${batchId}`))
      else await request(meta.delete(`running/${batchId}`))
    },
    running: async (batchId) => ((await request(tx(['meta'], 'readonly').objectStore('meta').get(`running/${batchId}`))) as string | undefined) ?? null,
  }
}

/** IndexedDB when this browser allows it (and persistent storage when it grants it), else memory for this page. */
export async function openMotionStore(): Promise<MotionStore> {
  try {
    if (typeof indexedDB === 'undefined') return memoryStore()
    const store = idbStore(await openDb())
    try {
      await navigator.storage?.persist?.()
    } catch {
      // Best effort: without it the browser may evict the exports under storage pressure.
    }
    return store
  } catch {
    return memoryStore()
  }
}
