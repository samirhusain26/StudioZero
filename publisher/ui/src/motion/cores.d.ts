// The repo's pure .mjs cores (tested in Node: tools/package-regression.mjs, tools/tests); the UI types only what it calls.
// Vite resolves @studio/* to the repo root (vite.config.ts).
declare module '@studio/tools/package-core.mjs' {
  export function renderErrors(render: unknown, opts: { folder: string; project: unknown; known: Set<string> }): string[]
  export function batchDocument(opts: { project: unknown; batchId: string; createdAt: string; commit: string; dirty: boolean; packaged: unknown }): string
}
declare module '@studio/projects/scalargame/package-core.mjs' {
  export function scalargameEpisodes(opts: {
    renders: unknown[]
    project: unknown
    studio: unknown
    config: unknown
    setName: string
    doc: unknown
    beds: unknown
    verification: unknown
    verReport: string
    recipe: (styleId: string) => unknown
    dry: boolean
  }): { generator: Record<string, unknown>; fields: Record<string, unknown>; episodes: { episodeId: string }[] }
}
declare module '@studio/engines/motion/pipeline/render-json-core.mjs' {
  export function motionRenderJsonCore(opts: {
    input: unknown
    createdAt: string
    job: Record<string, unknown>
    video: Record<string, unknown>
    cover: { sha256: string; bytes: number }
    bed: unknown
    bedId: string
    fonts: string[]
  }): Record<string, unknown>
}
