// Dev-only harness (never built into publisher/app/static): exposes the Studio's real export code and the raw render
// paths to Playwright, so exports and stills can be compared with render.sh. Assets come from engines/motion/public
// (vite.harness.config.ts publicDir), so staticFile() needs no base here.
import { renderMediaOnWeb, renderStillOnWeb } from '@remotion/web-renderer'
import { LibraryEpisode, calculateLibraryMetadata, type LibraryEpisodeProps } from '../src/motion/kit'
import { exportEpisode, FPS, HEIGHT, WIDTH } from '../src/motion/engine'
import type { JobBundle, JobInput } from '../src/motion/bundle'
import { packageWebBatch, webRenderJson, type ExportedFiles } from '../src/motion/webPackage'

declare global {
  interface Window {
    harnessStill: (props: LibraryEpisodeProps, frame: number, htmlInCanvas?: boolean) => Promise<string>
    harnessRender: (props: LibraryEpisodeProps, options: Record<string, unknown>) => Promise<string>
    harnessExport: (job: JobInput) => Promise<{ mp4: string; cover: string; measures: unknown; errors: string[]; master: unknown; primingSamples: number; seconds: number; files: unknown }>
    harnessDecode: (dataUrl: string) => Promise<{ sampleRate: number; length: number; channels: number; firstAbove: number }>
  }
}

const composition = (props: LibraryEpisodeProps) => ({
  id: 'LibraryEpisode',
  component: LibraryEpisode,
  durationInFrames: props.durationInFrames,
  fps: FPS,
  width: WIDTH,
  height: HEIGHT,
  calculateMetadata: calculateLibraryMetadata,
})

function toDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
}

window.harnessStill = async (props, frame, htmlInCanvas = false) => {
  const still = await renderStillOnWeb({ composition: composition(props), inputProps: props, frame, licenseKey: 'free-license', allowHtmlInCanvas: htmlInCanvas } as never)
  return toDataUrl(await still.blob({ format: 'png' }))
}

window.harnessRender = async (props, options) => {
  const result = await renderMediaOnWeb({ composition: composition(props), inputProps: props, licenseKey: 'free-license', ...options } as never)
  return toDataUrl(await result.getBlob())
}

window.harnessExport = async (job) => {
  const r = await exportEpisode(job, { staticBase: null })
  return { ...r, mp4: await toDataUrl(r.mp4), cover: await toDataUrl(r.cover) }
}

window.harnessDecode = async (dataUrl) => {
  const bytes = await (await fetch(dataUrl)).arrayBuffer()
  const ctx = new OfflineAudioContext({ numberOfChannels: 2, length: 48000, sampleRate: 48000 })
  const buffer = await ctx.decodeAudioData(bytes)
  const ch = buffer.getChannelData(0)
  let firstAbove = -1
  for (let i = 0; i < ch.length; i++) if (Math.abs(ch[i] ?? 0) > 0.01) { firstAbove = i; break }
  return { sampleRate: buffer.sampleRate, length: buffer.length, channels: buffer.numberOfChannels, firstAbove }
}
document.title = 'Motion harness ready'

declare global {
  interface Window {
    harnessPackage: (bundle: JobBundle, files: Record<string, ExportedFiles>, commit: string) => string
  }
}
window.harnessPackage = (bundle, files, commit) => {
  const renders = bundle.jobs.map((job) => webRenderJson(bundle, job, files[job.episodeId] as ExportedFiles, commit))
  return packageWebBatch(bundle, renders, { createdAt: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'), commit })
}

declare global {
  interface Window {
    harnessRenderJsons: (bundle: JobBundle, files: Record<string, ExportedFiles>, commit: string) => Record<string, unknown>[]
  }
}
window.harnessRenderJsons = (bundle, files, commit) => bundle.jobs.map((job) => webRenderJson(bundle, job, files[job.episodeId] as ExportedFiles, commit))
