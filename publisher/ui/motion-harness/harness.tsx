// Dev-only harness (never built into publisher/app/static): exposes the browser render paths to Playwright so stills and
// exports can be compared with render.sh. Assets come from engines/motion/public (vite.harness.config.ts publicDir).
import { renderMediaOnWeb, renderStillOnWeb } from '@remotion/web-renderer'
import { FPS, HEIGHT, LibraryEpisode, WIDTH, calculateLibraryMetadata, type LibraryEpisodeProps } from '../src/motion/kit'

declare global {
  interface Window {
    harnessStill: (props: LibraryEpisodeProps, frame: number, htmlInCanvas?: boolean) => Promise<string>
    harnessRender: (props: LibraryEpisodeProps, options: Record<string, unknown>) => Promise<string>
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
  const still = await renderStillOnWeb({
    composition: composition(props),
    inputProps: props,
    frame,
    licenseKey: 'free-license',
    allowHtmlInCanvas: htmlInCanvas,
  } as never)
  return toDataUrl(await still.blob({ format: 'png' }))
}

window.harnessRender = async (props, options) => {
  const result = await renderMediaOnWeb({ composition: composition(props), inputProps: props, licenseKey: 'free-license', ...options } as never)
  return toDataUrl(await result.getBlob())
}
document.title = 'Motion harness ready'

declare global {
  interface Window {
    harnessDecode: (dataUrl: string) => Promise<{ sampleRate: number; length: number; channels: number; firstAbove: number }>
  }
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
