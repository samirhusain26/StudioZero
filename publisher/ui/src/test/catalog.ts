import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { Catalog } from '../api/types'

/** The committed publisher/catalog.json, as GET /api/catalog serves it (Vitest runs from publisher/ui). A fresh copy per call. */
export function realCatalog(): Catalog {
  return JSON.parse(readFileSync(resolve(process.cwd(), '../catalog.json'), 'utf8')) as Catalog
}
